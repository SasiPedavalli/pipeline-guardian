"""
tests/test_data_quality.py

Unit tests for data_quality.py. These are pure-function tests with no
mocking required -- data_quality.py has no I/O or network dependencies.

Run with: pytest tests/
"""

import pandas as pd

from data_quality import (
    check_nulls,
    check_duplicates,
    check_schema_drift,
    check_freshness,
)


# ---------------------------------------------------------------------
# check_nulls
# ---------------------------------------------------------------------

class TestCheckNulls:
    def test_empty_dataframe(self):
        df = pd.DataFrame({"a": [], "b": []})
        result = check_nulls(df)
        assert result["total_rows"] == 0
        assert result["columns_with_nulls"] == {}

    def test_column_all_nulls(self):
        df = pd.DataFrame({"a": [None, None, None]})
        result = check_nulls(df)
        assert result["total_rows"] == 3
        assert result["columns_with_nulls"]["a"]["null_count"] == 3
        assert result["columns_with_nulls"]["a"]["null_rate"] == 1.0

    def test_column_with_no_nulls_is_excluded(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = check_nulls(df)
        assert "a" not in result["columns_with_nulls"]


# ---------------------------------------------------------------------
# check_duplicates
# ---------------------------------------------------------------------

class TestCheckDuplicates:
    def test_no_duplicates(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = check_duplicates(df)
        assert result["duplicate_row_count"] == 0
        assert result["duplicate_rate"] == 0.0

    def test_full_row_duplicates(self):
        df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
        result = check_duplicates(df)
        assert result["duplicate_row_count"] == 2
        assert result["checked_columns"] == "all columns"

    def test_duplicates_scoped_to_subset(self):
        df = pd.DataFrame({
            "order_id": [1, 1, 2],
            "amount": [10, 20, 30],
        })
        full_result = check_duplicates(df)
        assert full_result["duplicate_row_count"] == 0

        subset_result = check_duplicates(df, subset=["order_id"])
        assert subset_result["duplicate_row_count"] == 2
        assert subset_result["checked_columns"] == ["order_id"]


# ---------------------------------------------------------------------
# check_schema_drift
# ---------------------------------------------------------------------

class TestCheckSchemaDrift:
    def test_missing_column(self):
        df = pd.DataFrame({"a": [1, 2]})
        expected = {"a": "int64", "b": "object"}
        result = check_schema_drift(df, expected)
        assert result["missing_columns"] == ["b"]
        assert result["drift_detected"] is True

    def test_unexpected_extra_column(self):
        df = pd.DataFrame({"a": [1, 2], "extra": [3, 4]})
        expected = {"a": "int64"}
        result = check_schema_drift(df, expected)
        assert result["unexpected_columns"] == ["extra"]
        assert result["drift_detected"] is True

    def test_type_mismatch(self):
        df = pd.DataFrame({"a": ["1", "2"]})
        expected = {"a": "int64"}
        result = check_schema_drift(df, expected)
        assert result["type_mismatches"]["a"]["expected"] == "int64"
        assert result["type_mismatches"]["a"]["actual"] == "object"
        assert result["drift_detected"] is True

    def test_no_drift_when_schema_matches(self):
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        expected = {"a": "int64", "b": "object"}
        result = check_schema_drift(df, expected)
        assert result["missing_columns"] == []
        assert result["unexpected_columns"] == []
        assert result["type_mismatches"] == {}
        assert result["drift_detected"] is False

    def test_known_limitation_null_upcasts_int_column(self):
        """
        Documents pandas behavior: an otherwise-whole-number column that
        contains a null is upcast from int64 to float64, since the legacy
        (non-nullable) int dtype cannot represent NaN. That upcast will
        show up here as a reported type mismatch even though the
        underlying values are still logically integers -- this test
        exists to make that tradeoff explicit rather than fix it.
        """
        df = pd.DataFrame({"order_id": [1, 2, None]})
        assert str(df["order_id"].dtype) == "float64"

        expected = {"order_id": "int64"}
        result = check_schema_drift(df, expected)
        assert result["type_mismatches"]["order_id"]["actual"] == "float64"
        assert result["drift_detected"] is True


# ---------------------------------------------------------------------
# check_freshness
# ---------------------------------------------------------------------

class TestCheckFreshness:
    def test_missing_timestamp_column(self):
        df = pd.DataFrame({"a": [1, 2]})
        result = check_freshness(df, "timestamp_col")
        assert "error" in result

    def test_all_null_timestamp_column(self):
        df = pd.DataFrame({"ts": [None, None]})
        result = check_freshness(df, "ts")
        assert "error" in result

    def test_fresh_record_within_sla(self):
        now = pd.Timestamp.now(tz="UTC")
        df = pd.DataFrame({"ts": [now - pd.Timedelta(hours=1)]})
        result = check_freshness(df, "ts", max_age_hours=24)
        assert result["stale"] is False

    def test_stale_record_outside_sla(self):
        now = pd.Timestamp.now(tz="UTC")
        df = pd.DataFrame({"ts": [now - pd.Timedelta(hours=48)]})
        result = check_freshness(df, "ts", max_age_hours=24)
        assert result["stale"] is True

    def test_tz_naive_timestamp_is_handled(self):
        naive_now = pd.Timestamp.now()
        df = pd.DataFrame({"ts": [naive_now - pd.Timedelta(hours=1)]})
        result = check_freshness(df, "ts", max_age_hours=24)
        assert "error" not in result
        assert result["stale"] is False

    def test_tz_aware_timestamp_is_handled(self):
        aware_now = pd.Timestamp.now(tz="US/Eastern")
        df = pd.DataFrame({"ts": [aware_now - pd.Timedelta(hours=1)]})
        result = check_freshness(df, "ts", max_age_hours=24)
        assert "error" not in result
        assert result["stale"] is False
