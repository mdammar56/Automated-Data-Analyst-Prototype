"""
backend/cleaning/normalization.py

Automatic column-name standardization (Section 14). Produces a mapping of
original -> standardized names for the audit log, and guarantees unique,
SQL-safe identifiers regardless of the source dataset's naming style.
"""
from __future__ import annotations

import pandas as pd

from backend.utils.validators import to_safe_sql_identifier, dedupe_identifiers


def standardize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Return a copy of df with standardized column names, plus the
    original -> standardized mapping."""
    raw_names = [str(c) for c in df.columns]
    safe_names = [to_safe_sql_identifier(name, fallback=f"column_{i}") for i, name in enumerate(raw_names)]
    unique_names = dedupe_identifiers(safe_names)

    mapping = dict(zip(raw_names, unique_names))
    renamed = df.copy()
    renamed.columns = unique_names
    return renamed, mapping
