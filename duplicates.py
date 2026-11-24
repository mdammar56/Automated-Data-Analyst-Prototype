"""
backend/cleaning/duplicates.py

Duplicate detection (Section 16.2). Exact duplicates are safe to report and
remove automatically. "Possible" duplicates based on a user-selected subset
of identifying columns are only reported — never silently deleted, since
ambiguous matches require a human decision.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


def count_exact_duplicates(df: pd.DataFrame) -> int:
    return int(df.duplicated(keep="first").sum())


def remove_exact_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    before = len(df)
    out = df.drop_duplicates(keep="first")
    return out, before - len(out)


def count_possible_duplicates(df: pd.DataFrame, subset: Optional[list[str]]) -> int:
    if not subset:
        return 0
    valid_subset = [c for c in subset if c in df.columns]
    if not valid_subset:
        return 0
    return int(df.duplicated(subset=valid_subset, keep="first").sum())


def possible_duplicate_report(df: pd.DataFrame, subset: Optional[list[str]]) -> dict[str, Any]:
    count = count_possible_duplicates(df, subset)
    return {
        "subset": subset or [],
        "possible_duplicate_count": count,
        "note": "Possible duplicates are reported only. Removal requires explicit user confirmation.",
    }
