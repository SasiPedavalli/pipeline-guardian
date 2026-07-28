"""
agent.py

PipelineGuardian agent: gives Claude tool access to the data-quality checks
in data_quality.py, lets it decide which checks to run against a given
dataset, then asks it to synthesize a plain-English diagnosis and
remediation plan — the way a senior data engineer would triage a pipeline
alert.
"""

from __future__ import annotations
import json
import os
import pandas as pd
from anthropic import (
    Anthropic,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    APIStatusError,
)

from data_quality import CHECK_REGISTRY

MODEL = "claude-sonnet-4-6"

TOOLS = [
    {
        "name": "check_nulls",
        "description": "Check null/missing value rates for every column in the dataset.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_duplicates",
        "description": "Detect duplicate rows, optionally scoped to a subset of columns "
                        "(e.g. a business key like order_id).",
        "input_schema": {
            "type": "object",
            "properties": {
                "subset": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column names that together should be unique. "
                                    "Omit to check full-row duplicates.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "check_schema_drift",
        "description": "Compare the dataset's actual columns/dtypes against an expected schema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expected_schema": {
                    "type": "object",
                    "description": "Mapping of column name -> expected pandas dtype string, "
                                    "e.g. {\"order_id\": \"int64\", \"order_date\": \"object\"}",
                }
            },
            "required": ["expected_schema"],
        },
    },
    {
        "name": "check_freshness",
        "description": "Check whether the most recent record in a timestamp column falls "
                        "within an SLA window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timestamp_col": {"type": "string"},
                "max_age_hours": {"type": "number", "description": "SLA threshold in hours. Default 24."},
            },
            "required": ["timestamp_col"],
        },
    },
]

SYSTEM_PROMPT = """You are PipelineGuardian, a senior data engineer's AI assistant for \
triaging data quality issues in a pipeline. You have tools to check nulls, duplicates, \
schema drift, and freshness against a dataset.

Given a dataset description and (optionally) an expected schema, decide which checks are \
relevant and call them. Once you have enough results, produce a concise diagnosis:
1. **Summary** - one or two sentences on overall data health
2. **Issues found** - bullet list, each with severity (low/medium/high) and evidence from the checks
3. **Likely root cause** - your best inference given the pattern of issues
4. **Recommended fix** - concrete, actionable next step for each issue

Be direct and specific. Do not restate raw JSON back at the user - translate it into engineering language."""


class PipelineGuardian:
    def __init__(self, df: pd.DataFrame, api_key: str | None = None, max_turns: int = 6):
        self.df = df
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No Anthropic API key found. Set the ANTHROPIC_API_KEY environment "
                "variable, or pass api_key= explicitly when creating PipelineGuardian()."
            )
        self.client = Anthropic(api_key=resolved_key)
        self.max_turns = max_turns

    def _run_tool(self, name: str, tool_input: dict) -> dict:
        fn = CHECK_REGISTRY[name]
        if name == "check_schema_drift":
            return fn(self.df, tool_input["expected_schema"])
        if name == "check_duplicates":
            return fn(self.df, tool_input.get("subset"))
        if name == "check_freshness":
            return fn(self.df, tool_input["timestamp_col"], tool_input.get("max_age_hours", 24.0))
        return fn(self.df)

    def diagnose(self, dataset_description: str, expected_schema: dict | None = None) -> str:
        user_prompt = f"Dataset: {dataset_description}\n"
        user_prompt += f"Columns available: {list(self.df.columns)}\n"
        if expected_schema:
            user_prompt += f"Expected schema to validate against: {json.dumps(expected_schema)}\n"
        user_prompt += "\nRun the checks you think are relevant, then give your diagnosis."

        messages = [{"role": "user", "content": user_prompt}]

        for _ in range(self.max_turns):
            try:
                response = self.client.messages.create(
                    model=MODEL,
                    max_tokens=1500,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
            except AuthenticationError:
                return (
                    "PipelineGuardian error: authentication with the Anthropic API failed. "
                    "Check that ANTHROPIC_API_KEY is set to a valid, active key."
                )
            except RateLimitError:
                return (
                    "PipelineGuardian error: the Anthropic API rate limit was exceeded. "
                    "Wait a moment and try again, or check your account's usage tier."
                )
            except APIConnectionError:
                return (
                    "PipelineGuardian error: could not connect to the Anthropic API. "
                    "Check your network connection and try again."
                )
            except APIStatusError as e:
                return (
                    f"PipelineGuardian error: the Anthropic API returned an error "
                    f"(status {e.status_code}). {e.message}"
                )

            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text")

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})

        return "Reached tool-call limit without a final diagnosis — check logs."
