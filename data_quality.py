"""
data_quality.py

Core, dependency-light data quality checks that the agent calls as tools.
Each function returns a plain dict so results are easy to serialize and
easy for the model to reason over.
"""

from __future__ import annotations
import pandas as pd
from datetime import datetime, timezone


def check_nulls(df: pd.DataFrame) -> dict:
    """Null / missing value rate per column."""
    total_rows = len(df)
    null_counts = df.isnull().sum()
    result = {}
    for col, count in null_counts.items():
        if count > 0:
            result[col] = {
                "null_count": int(count),
                "null_rate": round(count / total_rows, 4) if total_rows else 0.0,
            }
    return {"total_rows": total_rows, "columns_with_nulls": result}


def check_duplicates(df: pd.DataFrame, subset: list[str] | None = None) -> dict:
    """Full-row or subset-based duplicate detection."""
    dup_mask = df.duplicated(subset=subset, keep=False)
    dup_count = int(dup_mask.sum())
    return {
        "duplicate_row_count": dup_count,
        "duplicate_rate": round(dup_count / len(df), 4) if len(df) else 0.0,
        "checked_columns": subset or "all columns",
    }


def check_schema_drift(df: pd.DataFrame, expected_schema: dict) -> dict:
    """
    Compares actual columns/dtypes against an expected schema definition.
    expected_schema example: {"order_id": "int64", "order_date": "object"}
    """
    actual = {col: str(dtype) for col, dtype in df.dtypes.items()}
    missing_columns = [c for c in expected_schema if c not in actual]
    unexpected_columns = [c for c in actual if c not in expected_schema]
    type_mismatches = {
        col: {"expected": expected_schema[col], "actual": actual[col]}
        for col in expected_schema
        if col in actual and actual[col] != expected_schema[col]
    }
    return {
        "missing_columns": missing_columns,
        "unexpected_columns": unexpected_columns,
        "type_mismatches": type_mismatches,
        "drift_detected": bool(missing_columns or unexpected_columns or type_mismatches),
    }


def check_freshness(df: pd.DataFrame, timestamp_col: str, max_age_hours: float = 24.0) -> dict:
    """Flags whether the most recent record falls outside an SLA window."""
    if timestamp_col not in df.columns:
        return {"error": f"column '{timestamp_col}' not found"}

    ts = pd.to_datetime(df[timestamp_col], errors="coerce")
    latest = ts.max()
    if pd.isna(latest):
        return {"error": f"no valid timestamps in '{timestamp_col}'"}

    now = datetime.now(timezone.utc)
    latest_utc = latest.tz_localize("UTC") if latest.tzinfo is None else latest.tz_convert("UTC")
    age_hours = round((now - latest_utc).total_seconds() / 3600, 2)

    return {
        "latest_record_timestamp": str(latest),
        "age_hours": age_hours,
        "sla_hours": max_age_hours,
        "stale": age_hours > max_age_hours,
    }


# Registry used by agent.py to expose these as Claude tool-use functions
CHECK_REGISTRY = {
    "check_nulls": check_nulls,
    "check_duplicates": check_duplicates,
    "check_schema_drift": check_schema_drift,
    "check_freshness": check_freshness,
}
