"""Tests for column standardization and the cleaning engine (Sections 14, 16)."""
import numpy as np
import pandas as pd

from backend.cleaning.duplicates import count_exact_duplicates, remove_exact_duplicates
from backend.cleaning.missing_values import apply_missing_value_strategy, normalize_placeholders
from backend.cleaning.normalization import standardize_columns
from backend.cleaning.outliers import detect_outliers
from backend.cleaning.anomalies import detect_anomalies
from backend.utils.column_detector import detect_dtype_and_role


def test_standardize_columns_basic():
    df = pd.DataFrame({"Customer Name": [1], "CUSTOMER AGE": [2], "Order-Date": [3]})
    renamed, mapping = standardize_columns(df)
    assert list(renamed.columns) == ["customer_name", "customer_age", "order_date"]
    assert mapping["Customer Name"] == "customer_name"


def test_standardize_columns_handles_collisions():
    df = pd.DataFrame({"Customer  Name": [1], "customer_name": [2]})
    renamed, mapping = standardize_columns(df)
    assert len(set(renamed.columns)) == 2


def test_normalize_placeholders_converts_to_nan():
    df = pd.DataFrame({"col": ["N/A", "none", "value", "", "unknown"]})
    out = normalize_placeholders(df)
    assert out["col"].isna().sum() == 4


def test_missing_value_strategy_numeric_uses_median():
    df = pd.DataFrame({"amount": [10.0, 20.0, np.nan, 30.0]})
    out, audit = apply_missing_value_strategy(df, {"amount": "numeric"})
    assert out["amount"].isna().sum() == 0
    assert out["amount"].iloc[2] == 20.0
    assert audit[0]["action"] == "filled_missing_numeric"


def test_exact_duplicate_detection_and_removal():
    df = pd.DataFrame({"a": [1, 1, 2], "b": [1, 1, 2]})
    assert count_exact_duplicates(df) == 1
    out, removed = remove_exact_duplicates(df)
    assert removed == 1
    assert len(out) == 2


def test_iqr_outlier_detection_flags_extreme_value():
    df = pd.DataFrame({"amount": [10, 12, 11, 13, 12, 10000]})
    result = detect_outliers(df, ["amount"])
    assert result["per_column"]["amount"]["combined_outliers"] >= 1


def test_anomaly_detection_requires_minimum_rows():
    df = pd.DataFrame({"a": range(5), "b": range(5)})
    result = detect_anomalies(df, ["a", "b"])
    assert result["eligible"] is False


def test_anomaly_detection_runs_with_enough_data():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"a": rng.normal(size=100), "b": rng.normal(size=100)})
    result = detect_anomalies(df, ["a", "b"])
    assert result["eligible"] is True
    assert "anomaly_count" in result


def test_column_role_detection_identifies_currency():
    series = pd.Series([10.5, 20.0, 30.25])
    detection = detect_dtype_and_role("total_sales", series)
    assert detection.role == "currency_amount"


def test_column_role_detection_identifies_identifier():
    series = pd.Series([f"ORD{i}" for i in range(20)])
    detection = detect_dtype_and_role("order_id", series)
    assert detection.role == "identifier"
