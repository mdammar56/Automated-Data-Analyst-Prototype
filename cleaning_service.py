"""
backend/services/cleaning_service.py

Orchestrates the cleaning engine: Detect -> Explain -> Recommend -> Preview
-> Apply (Section 17). Builds a preview plan without mutating data, and a
separate apply step that performs the transformations and writes a full
audit trail (Section 20).
"""
from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

import pandas as pd

from backend.cleaning.anomalies import detect_anomalies
from backend.cleaning.duplicates import (
    count_exact_duplicates,
    possible_duplicate_report,
    remove_exact_duplicates,
)
from backend.cleaning.missing_values import (
    apply_missing_value_strategy,
    build_missing_value_plan,
    normalize_placeholders,
)
from backend.cleaning.outliers import detect_outliers
from backend.schemas import CleaningOptions


def _summary(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "missing_cells": int(df.isna().sum().sum()),
        "duplicate_rows": count_exact_duplicates(df),
    }


def build_cleaning_preview(
    df: pd.DataFrame,
    column_roles: dict[str, str],
    numeric_columns: list[str],
    options: CleaningOptions,
) -> dict[str, Any]:
    before = _summary(df)
    missing_plan = build_missing_value_plan(df, column_roles) if options.handle_missing else []
    duplicate_count = count_exact_duplicates(df) if options.remove_exact_duplicates else 0
    possible_dupes = possible_duplicate_report(df, options.duplicate_subset)
    outlier_summary = detect_outliers(df, numeric_columns) if options.flag_outliers else {"per_column": {}, "total_flagged_rows": 0}
    anomaly_summary = detect_anomalies(df, numeric_columns) if options.run_anomaly_detection else {"eligible": False, "anomaly_count": 0}

    plan = [{"step": "missing_values", "detail": missing_plan}]
    if options.remove_exact_duplicates:
        plan.append({"step": "remove_exact_duplicates", "detail": {"rows_to_remove": duplicate_count}})
    plan.append({"step": "possible_duplicates_report", "detail": possible_dupes})
    if options.flag_outliers:
        plan.append({"step": "flag_outliers", "detail": outlier_summary["per_column"]})
    if options.run_anomaly_detection:
        plan.append({"step": "anomaly_detection", "detail": {
            "eligible": anomaly_summary.get("eligible", False),
            "reason": anomaly_summary.get("reason"),
            "anomaly_count": anomaly_summary.get("anomaly_count", 0),
        }})

    estimated_after = dict(before)
    estimated_after["rows"] = before["rows"] - duplicate_count
    estimate = normalize_placeholders(df) if options.fix_invalid_values else df.copy()
    if options.remove_exact_duplicates:
        estimate, _ = remove_exact_duplicates(estimate)
    if options.handle_missing:
        estimate, _ = apply_missing_value_strategy(estimate, column_roles)
    estimated_after.update(_summary(estimate))

    return {
        "plan": plan,
        "before_summary": before,
        "estimated_after_summary": estimated_after,
    }


def apply_cleaning(
    dataset_id: str,
    df: pd.DataFrame,
    column_roles: dict[str, str],
    numeric_columns: list[str],
    options: CleaningOptions,
) -> dict[str, Any]:
    before = _summary(df)
    working = normalize_placeholders(df) if options.fix_invalid_values else df.copy()
    audit_entries: list[dict[str, Any]] = []

    if options.remove_exact_duplicates:
        working, removed = remove_exact_duplicates(working)
        audit_entries.append({"action": "removed_exact_duplicates", "rows_removed": removed})

    if options.handle_missing:
        working, missing_audit = apply_missing_value_strategy(working, column_roles)
        audit_entries.extend(missing_audit)

    outlier_flags = pd.DataFrame(index=working.index)
    if options.flag_outliers:
        outlier_result = detect_outliers(working, numeric_columns)
        outlier_flags = outlier_result["flags"]
        working["_outlier_flag"] = outlier_flags.any(axis=1) if not outlier_flags.empty else False
        audit_entries.append({"action": "flagged_outliers", "total_flagged_rows": outlier_result["total_flagged_rows"]})

    if options.run_anomaly_detection:
        anomaly_result = detect_anomalies(working, numeric_columns)
        if anomaly_result.get("eligible"):
            working["_anomaly_flag"] = anomaly_result["flags"].reindex(working.index, fill_value=False)
            audit_entries.append({"action": "anomaly_detection", "anomaly_count": anomaly_result["anomaly_count"]})
        else:
            audit_entries.append({"action": "anomaly_detection_skipped", "reason": anomaly_result.get("reason")})

    after = _summary(working)
    # after-summary should reflect real missing count post-fill, recompute directly:
    after["missing_cells"] = int(working.isna().sum().sum())
    original_values = df.loc[working.index, df.columns]
    retained_values = working[df.columns]
    same = original_values.eq(retained_values) | (original_values.isna() & retained_values.isna())
    changed = ~same.fillna(False)
    audit_entries.append({"action": "transformation_summary", "rows_removed": len(df) - len(working),
                          "retained_rows_changed": int(changed.any(axis=1).sum()),
                          "values_changed": int(changed.sum().sum()),
                          "flag_columns_added": [c for c in working.columns if c not in df.columns]})

    return {
        "cleaned_df": working,
        "before": before,
        "after": after,
        "audit_log": [{"timestamp": datetime.now(timezone.utc).isoformat(), "action": e["action"], "detail": {k: v for k, v in e.items() if k != "action"}} for e in audit_entries],
    }
