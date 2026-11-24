"""Opt-in live PostgreSQL checks: only session-local temporary tables, no user-table writes."""
import os
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import database
from backend.api.sql_routes import run_query
from backend.schemas import SqlQueryRequest

pytestmark = pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS") != "1", reason="Set RUN_POSTGRES_TESTS=1 for session-local PostgreSQL fixtures")


@pytest.fixture
def connection(monkeypatch):
    engine = database.get_engine()
    with engine.connect() as conn:
        conn.exec_driver_sql('CREATE TEMP TABLE phase1_sql_fixture (customer_id integer, amount double precision)')
        conn.exec_driver_sql('INSERT INTO phase1_sql_fixture SELECT mod(i, 4), i * 1.5 FROM generate_series(1, 20) AS i')
        conn.commit()
        @contextmanager
        def begin():
            with conn.begin():
                yield conn
        monkeypatch.setattr(database, "get_engine", lambda: SimpleNamespace(begin=begin))
        yield conn
        # Temporary table belongs only to this connection and vanishes when disposed.
    engine.dispose()


def test_live_cte_window_aggregation_and_limit(connection):
    query = '''WITH ranked AS (
      SELECT customer_id, amount, ROW_NUMBER() OVER(PARTITION BY customer_id ORDER BY amount DESC) AS rn
      FROM pg_temp.phase1_sql_fixture
    ) SELECT customer_id, SUM(amount) AS total FROM ranked WHERE rn <= 2 GROUP BY customer_id ORDER BY customer_id'''
    result = run_query(SqlQueryRequest(query=query, limit=2), confirm=False)
    assert result.truncated and result.row_count == 2
    assert result.rows[0] == [0, 54.0]


@pytest.mark.parametrize("query,message", [
    ('SELECT * FROM phase1_missing_schema.phase1_sql_fixture', 'Table not found'),
    ('SELECT absent_column FROM pg_temp.phase1_sql_fixture', 'Column not found'),
    ('SELECT pg_sleep(0.5)', 'timed out'),
])
def test_live_errors_and_timeout(connection, query, message):
    with pytest.raises(HTTPException) as exc:
        run_query(SqlQueryRequest(query=query, timeout_ms=100), confirm=False)
    assert message in exc.value.detail


def test_confirmed_write_commits_to_temporary_fixture(connection):
    with pytest.raises(HTTPException) as exc:
        run_query(SqlQueryRequest(query='DELETE FROM pg_temp.phase1_sql_fixture WHERE customer_id=0'), confirm=False)
    assert exc.value.status_code == 409
    run_query(SqlQueryRequest(query='DELETE FROM pg_temp.phase1_sql_fixture WHERE customer_id=0'), confirm=True)
    result = run_query(SqlQueryRequest(query='SELECT count(*) FROM pg_temp.phase1_sql_fixture'), confirm=False)
    assert result.rows == [[15]]


def test_live_literal_percent_and_colon_preserved(connection):
    result = run_query(SqlQueryRequest(query="SELECT 5 % 2, ':name', '100%'"), confirm=False)
    assert result.rows == [[1, ':name', '100%']]


def test_live_load_types_and_metadata_refresh_rolled_back(monkeypatch):
    import uuid
    import pandas as pd
    from backend.services.database_service import load_dataframe_to_postgres
    from backend.api.database_routes import database_metadata
    engine = database.get_engine()
    table = "phase1_test_" + uuid.uuid4().hex
    with engine.connect() as conn:
        transaction = conn.begin()
        @contextmanager
        def begin():
            yield conn
        monkeypatch.setattr(database, "get_engine", lambda: SimpleNamespace(begin=begin))
        try:
            result = load_dataframe_to_postgres(pd.DataFrame({"Customer ID": [1, 2], "Amount": [2.5, 3.5]}), table, {"Customer ID": "integer", "Amount": "float"})
            assert result["rows_loaded"] == 2
            entry = next(t for t in database_metadata()["tables"] if t["reference"] == f'"public"."{table}"')
            assert [c["type"] for c in entry["columns"]] == ["bigint", "double precision"]
            assert conn.exec_driver_sql(f'SELECT SUM(amount) FROM public."{table}"').scalar() == 6.0
        finally:
            # Roll back only this test's new table and rows, including its DDL.
            transaction.rollback()
