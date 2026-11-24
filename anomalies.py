"""
backend/cleaning/anomalies.py

Thin wrapper around the ML anomaly-detection module so the cleaning engine
has a single, consistent entry point (Section 16.5). Delegates the actual
Isolation Forest / Local Outlier Factor logic to backend.ml.anomaly_detection.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.ml.anomaly_detection import run_isolation_forest, run_local_outlier_factor

MIN_ROWS_FOR_ML = 30
MIN_NUMERIC_COLUMNS = 2


def detect_anomalies(df: pd.DataFrame, numeric_columns: list[str]) -> dict[str, Any]:
    usable_columns = [c for c in numeric_columns if c in df.columns]
    if len(df) < MIN_ROWS_FOR_ML or len(usable_columns) < MIN_NUMERIC_COLUMNS:
        return {
            "eligible": False,
            "reason": (
                f"Anomaly detection requires at least {MIN_ROWS_FOR_ML} rows and "
                f"{MIN_NUMERIC_COLUMNS} numeric columns; dataset has {len(df)} rows "
                f"and {len(usable_columns)} usable numeric columns."
            ),
            "anomaly_count": 0,
            "flags": pd.Series(False, index=df.index),
        }

    iso_result = run_isolation_forest(df, usable_columns)
    lof_result = run_local_outlier_factor(df, usable_columns)

    return {
        "eligible": True,
        "columns_used": usable_columns,
        "isolation_forest": {
            "anomaly_count": int(iso_result["flags"].sum()),
        },
        "local_outlier_factor": {
            "anomaly_count": int(lof_result["flags"].sum()),
        },
        "anomaly_count": int(iso_result["flags"].sum()),
        "flags": iso_result["flags"],
        "scores": iso_result["scores"],
    }
