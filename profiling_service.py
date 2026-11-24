"""
backend/services/profiling_service.py

Automatic dataset profiling (Section 13) combined with column standardization
(Section 14) and type/role detection (Section 15). This is the first stage a
freshly uploaded dataset passes through.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.cleaning.duplicates import count_exact_duplicates
from backend.cleaning.missing_values import normalize_placeholders, missing_value_report
from backend.cleaning.normalization import standardize_columns
from backend.cleaning.outliers import detect_outliers
from backend.utils.column_detector import detect_dtype_and_role
from backend.utils.logger import audit_log


def profile_dataset(dataset_id: str, raw_df: pd.DataFrame) -> dict[str, Any]:
    df, mapping = standardize_columns(raw_df)
    df = normalize_placeholders(df)

    audit_log.add(dataset_id, "column_standardization", {"mapping": mapping})

    roles: dict[str, str] = {}
    dtypes: dict[str, str] = {}
    column_profiles: list[dict[str, Any]] = []
    missing_report = missing_value_report(df)
    numeric_columns: list[str] = []

    reverse_mapping = {v: k for k, v in mapping.items()}

    for col in df.columns:
        detection = detect_dtype_and_role(col, df[col])
        roles[col] = detection.role
        dtypes[col] = detection.dtype
        if detection.role in ("numeric", "currency_amount", "percentage_rate"):
            numeric_columns.append(col)

        sample_values = df[col].dropna().astype(str).unique()[:5].tolist()
        column_profiles.append({
            "original_name": reverse_mapping.get(col, col),
            "standardized_name": col,
            "detected_type": detection.dtype,
            "detected_role": detection.role,
            "missing_count": missing_report[col]["missing_count"],
            "missing_percent": missing_report[col]["missing_percent"],
            "unique_count": int(df[col].nunique(dropna=True)),
            "sample_values": sample_values,
            "stats": detection.stats,
        })

    duplicate_rows = count_exact_duplicates(df)
    total_cells = df.shape[0] * df.shape[1]
    missing_cells = int(df.isna().sum().sum())

    correlation: dict[str, dict[str, float]] = {}
    if len(numeric_columns) >= 2:
        numeric_df = df[numeric_columns].apply(pd.to_numeric, errors="coerce")
        corr_matrix = numeric_df.corr(numeric_only=True).round(3)
        corr_matrix = corr_matrix.replace({np.nan: 0.0})
        correlation = corr_matrix.to_dict()

    outlier_summary = detect_outliers(df, numeric_columns)

    audit_log.add(dataset_id, "profiling_complete", {
        "rows": df.shape[0],
        "columns": df.shape[1],
        "duplicate_rows": duplicate_rows,
        "missing_cells": missing_cells,
    })

    return {
        "dataset_id": dataset_id,
        "rows": df.shape[0],
        "columns": df.shape[1],
        "duplicate_rows": duplicate_rows,
        "missing_cells": missing_cells,
        "missing_percent": round((missing_cells / total_cells) * 100, 2) if total_cells else 0.0,
        "column_profiles": column_profiles,
        "correlation": correlation,
        "outlier_summary": outlier_summary["per_column"],
        "numeric_columns": numeric_columns,
        "_standardized_df": df,       # internal use only, stripped before API response
        "_column_mapping": mapping,   # internal use only
        "_column_roles": roles,
        "_column_dtypes": dtypes,
    }
