"""
backend/cleaning/missing_values.py

Missing-value detection and handling (Section 16.1). Strategy is chosen
according to the detected data type / role rather than a single global rule:
  - Numeric: median (robust to outliers) is used by default.
  - Categorical: mode, or an explicit "Unknown" label when no dominant mode.
  - Date/time: left as missing; dates are never invented.
  - Text/identifier: left as missing (or "Unknown" for text).

Common placeholder strings (e.g. "N/A", "none", "null", "-") are treated as
missing before any statistics are computed.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

PLACEHOLDER_VALUES = {
    "", "na", "n/a", "n\\a", "null", "none", "nan", "-", "--", "?", "unknown", "undefined",
}


def normalize_placeholders(df: pd.DataFrame) -> pd.DataFrame:
    """Convert common missing-value placeholder strings into real NaNs."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_object_dtype(out[col]) or pd.api.types.is_string_dtype(out[col]):
            stripped = out[col].astype(str).str.strip()
            mask = stripped.str.lower().isin(PLACEHOLDER_VALUES)
            out.loc[mask, col] = np.nan
    return out


def missing_value_report(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    n = len(df)
    for col in df.columns:
        missing = int(df[col].isna().sum())
        report[col] = {
            "missing_count": missing,
            "missing_percent": round((missing / n) * 100, 2) if n else 0.0,
        }
    return report


def build_missing_value_plan(df: pd.DataFrame, column_roles: dict[str, str]) -> list[dict[str, Any]]:
    """Describe, without applying, how each column with missing values would
    be handled (Detect -> Explain -> Recommend -> Preview -> Apply)."""
    plan = []
    report = missing_value_report(df)
    for col, info in report.items():
        if info["missing_count"] == 0:
            continue
        role = column_roles.get(col, "unknown")
        if role in ("numeric", "currency_amount", "percentage_rate"):
            strategy, reason = "median_fill", "Median is robust to skew and outliers."
        elif role == "categorical":
            strategy, reason = "mode_fill_or_unknown", "Most frequent category, or 'Unknown' if no clear mode."
        elif role == "date_time":
            strategy, reason = "leave_missing", "Dates are never invented without a defensible rule."
        elif role == "text":
            strategy, reason = "unknown_label", "Missing text is labeled 'Unknown' rather than guessed."
        else:
            strategy, reason = "leave_missing", "Unrecognized column role; left untouched for manual review."
        plan.append({
            "column": col,
            "role": role,
            "missing_count": info["missing_count"],
            "missing_percent": info["missing_percent"],
            "strategy": strategy,
            "reason": reason,
        })
    return plan


def apply_missing_value_strategy(
    df: pd.DataFrame, column_roles: dict[str, str]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    out = df.copy()
    audit: list[dict[str, Any]] = []
    for col in out.columns:
        missing_before = int(out[col].isna().sum())
        if missing_before == 0:
            continue
        role = column_roles.get(col, "unknown")

        if role in ("numeric", "currency_amount", "percentage_rate"):
            fill_value = out[col].median()
            out[col] = out[col].fillna(fill_value)
            audit.append({"column": col, "action": "filled_missing_numeric",
                          "fill_value": None if pd.isna(fill_value) else float(fill_value),
                          "count": missing_before - int(out[col].isna().sum())})
        elif role == "categorical":
            mode_series = out[col].mode(dropna=True)
            fill_value = mode_series.iloc[0] if not mode_series.empty else "Unknown"
            out[col] = out[col].fillna(fill_value)
            audit.append({"column": col, "action": "filled_missing_categorical",
                          "fill_value": str(fill_value), "count": missing_before})
        elif role == "text":
            out[col] = out[col].fillna("Unknown")
            audit.append({"column": col, "action": "filled_missing_text",
                          "fill_value": "Unknown", "count": missing_before})
        else:
            audit.append({"column": col, "action": "left_missing", "count": missing_before})
    return out, audit
