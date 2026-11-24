"""
backend/services/schema_service.py

Maps detected pandas dtypes to suitable PostgreSQL column types and builds
a safe CREATE TABLE statement using validated, standardized identifiers
(Section 21). Table/column names are validated before being interpolated,
since PostgreSQL identifiers cannot be bound as query parameters.
"""
from __future__ import annotations

import pandas as pd

from backend.utils.validators import to_safe_sql_identifier

PANDAS_TO_PG = {
    "integer": "BIGINT",
    "float": "DOUBLE PRECISION",
    "numeric": "DOUBLE PRECISION",
    "datetime": "TIMESTAMP",
    "categorical": "TEXT",
    "text": "TEXT",
    "identifier": "TEXT",
    "unknown": "TEXT",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
    "int64": "BIGINT",
    "int32": "INTEGER",
    "float64": "DOUBLE PRECISION",
    "float32": "REAL",
}


def build_table_name(filename_or_hint: str) -> str:
    stem = filename_or_hint.rsplit(".", 1)[0] if "." in filename_or_hint else filename_or_hint
    return to_safe_sql_identifier(stem, fallback="dataset_table")


def infer_pg_type(dtype_label: str) -> str:
    cleaned_label = str(dtype_label).strip().lower()
    if cleaned_label in PANDAS_TO_PG:
        return PANDAS_TO_PG[cleaned_label]
    if cleaned_label.upper() in set(PANDAS_TO_PG.values()):
        return cleaned_label.upper()
    return PANDAS_TO_PG.get(cleaned_label, "TEXT")


def infer_pg_type_from_series(series: pd.Series) -> str:
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"
    non_null = series.dropna()
    if not non_null.empty:
        sample = non_null.iloc[0]
        if isinstance(sample, bool):
            return "BOOLEAN"
    return "TEXT"


def build_create_table_sql(table_name: str, column_dtypes: dict[str, str]) -> str:
    safe_table = to_safe_sql_identifier(table_name, fallback="dataset_table")
    column_defs = []
    for col, dtype_label in column_dtypes.items():
        safe_col = to_safe_sql_identifier(col, fallback="column")
        pg_type = infer_pg_type(dtype_label)
        column_defs.append(f'"{safe_col}" {pg_type}')
    columns_sql = ",\n    ".join(column_defs)
    return f'CREATE TABLE IF NOT EXISTS "{safe_table}" (\n    {columns_sql}\n);'

