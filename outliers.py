"""
backend/cleaning/outliers.py

Univariate outlier detection (Section 16.4). Outliers are always *marked*,
never automatically deleted — a statistically extreme value (e.g. a very
large purchase amount) may be a genuine, valuable business observation.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def iqr_outlier_mask(series: pd.Series, k: float = 1.5) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce") if series.dtype == bool else series
    non_null = series.dropna().astype(float)
    if len(non_null) < 4:
        return pd.Series(False, index=series.index)
    q1, q3 = np.nanpercentile(non_null, [25, 75])
    iqr = q3 - q1
    lower, upper = q1 - k * iqr, q3 + k * iqr
    return (series < lower) | (series > upper)


def zscore_outlier_mask(series: pd.Series, threshold: float = 3.0) -> pd.Series:
    numeric_series = pd.to_numeric(series, errors="coerce")
    non_null = numeric_series.dropna()
    if len(non_null) < 4 or non_null.std(ddof=0) == 0:
        return pd.Series(False, index=series.index)
    mean, std = non_null.mean(), non_null.std(ddof=0)
    z = (numeric_series - mean) / std
    return z.abs() > threshold



def detect_outliers(df: pd.DataFrame, numeric_columns: list[str]) -> dict[str, Any]:
    """Combine IQR and Z-score methods for each numeric column and mark rows
    flagged by either method. Returns a per-column summary plus a boolean
    'is_outlier_<col>' style flag column that can be attached for review."""
    summary: dict[str, Any] = {}
    flags = pd.DataFrame(index=df.index)

    for col in numeric_columns:
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        iqr_mask = iqr_outlier_mask(series)
        z_mask = zscore_outlier_mask(series)
        combined = iqr_mask | z_mask
        flags[col] = combined
        summary[col] = {
            "iqr_outliers": int(iqr_mask.sum()),
            "zscore_outliers": int(z_mask.sum()),
            "combined_outliers": int(combined.sum()),
        }

    total_flagged_rows = int(flags.any(axis=1).sum()) if not flags.empty else 0
    return {"per_column": summary, "total_flagged_rows": total_flagged_rows, "flags": flags}
