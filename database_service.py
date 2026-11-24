"""
backend/services/database_service.py

Implements the PostgreSQL Setup Wizard (Section 11) and safe bulk data
loading into a user-selected database (Section 21). Passwords are handled
entirely server-side; only status/booleans are ever returned to the browser.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text

from backend import database as db
from backend.config import get_settings
from backend.services.schema_service import (
    build_create_table_sql,
    build_table_name,
    infer_pg_type,
    infer_pg_type_from_series,
)
from backend.utils.logger import get_logger
from backend.utils.validators import dedupe_identifiers, to_safe_sql_identifier

logger = get_logger()


def run_setup_wizard(host: str, port: int, user: str, password: str, database: str) -> dict[str, Any]:
    safe_db = to_safe_sql_identifier(database, fallback="app_db")

    ok, message = db.test_connection(host, port, user, password, "postgres")
    if not ok:
        return {
            "success": False,
            "message": f"Could not reach PostgreSQL server: {message}",
            "database_created": False,
            "database_name": safe_db,
        }

    created = False
    if not db.database_exists(host, port, user, password, safe_db):
        try:
            db.create_database(host, port, user, password, safe_db)
            created = True
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "message": f"Could not create database '{safe_db}': {exc}",
                "database_created": False,
                "database_name": safe_db,
            }

    ok, message = db.test_connection(host, port, user, password, safe_db)
    if not ok:
        return {
            "success": False,
            "message": f"Database exists but connection failed: {message}",
            "database_created": created,
            "database_name": safe_db,
        }

    db.init_engine(host, port, user, password, safe_db)

    # Keep validated settings in memory; never overwrite the user's .env.
    settings = get_settings()
    settings.database_host = host
    settings.database_port = port
    settings.database_user = user
    settings.database_password = password
    settings.database_name = safe_db


    return {
        "success": True,
        "message": f"Connected to database '{safe_db}'.{' Database created.' if created else ''}",
        "database_created": created,
        "database_name": safe_db,
    }


def load_dataframe_to_postgres(df: pd.DataFrame, table_hint: str, column_dtypes: dict[str, str]) -> dict[str, Any]:
    table_name = build_table_name(table_hint)
    raw_cols = list(df.columns)
    safe_names = [to_safe_sql_identifier(c) for c in raw_cols]
    deduped_names = dedupe_identifiers(safe_names)
    rename_map = dict(zip(raw_cols, deduped_names))
    renamed = df.rename(columns=rename_map).copy()

    # Determine PostgreSQL data type for EVERY column in the DataFrame
    table_column_types: dict[str, str] = {}
    for orig_col, safe_col in rename_map.items():
        if orig_col in column_dtypes:
            table_column_types[safe_col] = infer_pg_type(column_dtypes[orig_col])
        elif safe_col in column_dtypes:
            table_column_types[safe_col] = infer_pg_type(column_dtypes[safe_col])
        else:
            table_column_types[safe_col] = infer_pg_type_from_series(renamed[safe_col])

    create_sql = build_create_table_sql(table_name, table_column_types)

    renamed = renamed.replace([float("inf"), float("-inf")], None)
    for col in renamed.columns:
        if renamed[col].dtype == object:
            renamed[col] = renamed[col].where(pd.notnull(renamed[col]), None)

    engine = db.get_engine()
    # DDL and insert succeed together; imports always use the explicit public schema.
    with engine.begin() as conn:
        conn.exec_driver_sql("SET LOCAL search_path TO public")
        conn.exec_driver_sql("SET LOCAL statement_timeout = '60000ms'")
        conn.execute(text(create_sql))
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = :tbl AND table_schema = 'public'"), {"tbl": table_name})
        existing_cols = set(result.scalars())
        for col, pg_type in table_column_types.items():
            if col not in existing_cols:
                conn.execute(text(f'ALTER TABLE "public"."{table_name}" ADD COLUMN "{col}" {pg_type}'))
        renamed.to_sql(table_name, conn, schema="public", if_exists="append", index=False, chunksize=1000, method="multi")
        total_rows = conn.execute(text(f'SELECT count(*) FROM "public"."{table_name}"')).scalar()

    current_db = db.get_current_database_name()
    return {
        "table_name": table_name,
        "rows_loaded": len(renamed),
        "columns": list(renamed.columns),
        "database_name": current_db,
        "total_table_rows": total_rows,
    }

