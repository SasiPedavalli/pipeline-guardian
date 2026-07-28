# PipelineGuardian 🛡️

An AI agent that triages data quality issues the way a senior data engineer would — built on the Claude API's tool-use capability, applied to the data observability problems I work on day to day (schema drift, freshness SLAs, null/duplicate rates across HR, financial, and operational pipelines).

Instead of hardcoding a fixed sequence of checks, the agent is given a **toolbox** of data quality functions and decides for itself which checks are relevant, runs them, then synthesizes the raw results into a plain-English diagnosis with severity ratings and a recommended fix — output a human engineer can act on immediately.

## Why this project

Most "data quality" tooling stops at producing a dashboard of red/green checks. The actual engineering work is interpreting *why* a check failed and what to do about it. This project pushes that interpretation step onto an LLM agent with real tool access to the data, closing the loop from "here's a null rate" to "here's what's probably broken and how to fix it."

## Architecture

| File | Purpose |
|---|---|
| main.py | Entry point / demo runner |
| agent.py | PipelineGuardian class — Claude tool-use orchestration loop |
| data_quality.py | Dependency-light quality check functions (the "tools") |
| sample_data/ | Example dataset with intentionally seeded issues |
| tests/ | Unit tests for the data quality checks |

The agent loop:
1. Claude receives a dataset description + column list (+ optional expected schema)
2. Claude decides which of the 4 tools to call: check_nulls, check_duplicates, check_schema_drift, check_freshness
3. Results are fed back to Claude as tool results
4. Claude repeats until it has enough evidence, then produces a structured diagnosis

## Setup

```bash
git clone https://github.com/pesasi86000/pipeline-guardian.git
cd pipeline-guardian
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python main.py
```

## Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

## Sample output

Illustrative example of the kind of diagnosis PipelineGuardian produces when run against `sample_data/orders.csv` (actual wording will vary between runs, since the agent generates it live):

```
============================================================
PIPELINEGUARDIAN DIAGNOSIS
============================================================
Summary: The orders feed has multiple data quality issues that need
attention before this data is safe to use downstream -- missing values,
an exact duplicate order, and an incomplete region field.

Issues found:
- [high] Duplicate order: order_id 1005 appears twice with identical
  values, which will double-count revenue if aggregated as-is.
- [medium] Missing values in customer_id, amount, order_date, and region
  across several rows -- enough to distort per-customer and per-region
  rollups.
- [low] order_id is stored as float64 instead of int64 due to a null in
  an unrelated row; this is a pandas artifact, not a data problem.

Likely root cause: an upstream retry or replay in the ingestion job
produced the duplicate row, while the missing fields point to an
incomplete write from the source system rather than a transformation bug.

Recommended fix:
- Deduplicate on order_id before loading into the warehouse.
- Add NOT NULL constraints (or a quarantine step) for customer_id,
  amount, and region at ingestion.
- Backfill or flag rows with missing order_date rather than dropping them.
```

## Tech

Python · pandas · Claude API (tool use / agentic loop)

## Author

**Sasi P** — Data Engineer, NYU Langone Health
[LinkedIn](https://www.linkedin.com/in/sasi-p68) · [GitHub](https://github.com/pesasi86000)
