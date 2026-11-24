"""Phase 1 regressions. All dataset writes use temporary directories."""
import io
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.main import app
from backend import database
from backend.api import cleaning_routes, profile_routes, sql_routes
from backend.schemas import CleaningOptions, SqlQueryRequest
from backend.services import file_service
from backend.ml.segmentation import kmeans_segments, compute_rfm
from backend.utils.validators import is_select_only, is_single_statement, dedupe_identifiers


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    settings = SimpleNamespace(upload_dir=tmp_path, cleaned_dir=tmp_path, upload_max_mb=1)
    monkeypatch.setattr(file_service, "get_settings", lambda: settings)
    monkeypatch.setattr(database, "is_connected", lambda: False)
    old = file_service.registry._datasets
    file_service.registry._datasets = {}
    yield TestClient(app)
    file_service.registry._datasets = old


def fixture_csv():
    frame = pd.DataFrame({"Client ID": [f"C{i%10}" for i in range(40)],
                          "Invoice Date": pd.date_range("2024-01-01", periods=40),
                          "Amount": [float(i*3+1) for i in range(40)],
                          "Quantity": [i%6+1 for i in range(40)],
                          "Notes": ['hello, "world"\nnext'] * 40})
    frame.loc[2, "Amount"] = np.nan
    return pd.concat([frame, frame.iloc[[0]]]).to_csv(index=False).encode()


def test_cleaning_repeat_concurrent_profile_and_original_preservation(isolated):
    ds = file_service.store_new_dataset("renamed data.csv", fixture_csv())
    original = ds.raw_df.copy(deep=True)
    profile_routes.get_profile(ds.dataset_id)
    options = CleaningOptions(run_anomaly_detection=False, confirm_destructive=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: cleaning_routes.apply_cleaning(ds.dataset_id, options), range(2)))
    assert results[0] == results[1]
    assert results[0].after["rows"] == 40
    cleaned = ds.cleaned_df.copy(deep=True)
    profile_routes.get_profile(ds.dataset_id)
    pd.testing.assert_frame_equal(cleaned, ds.cleaned_df)
    pd.testing.assert_frame_equal(original, ds.raw_df)
    preview = cleaning_routes.data_preview(ds.dataset_id)
    assert preview["cleaned"]["rows"][0][4] == 'hello, "world"\nnext'
    assert cleaning_routes.get_audit_log(ds.dataset_id) == results[0].audit_log


def test_cleaning_failure_preserves_prior_state(isolated, monkeypatch):
    ds = file_service.store_new_dataset("sample.csv", fixture_csv())
    profile_routes.get_profile(ds.dataset_id)
    before = ds.cleaned_df.copy()
    def fail(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(cleaning_routes, "persist_cleaned", fail)
    with pytest.raises(OSError):
        cleaning_routes.apply_cleaning(ds.dataset_id, CleaningOptions(run_anomaly_detection=False, confirm_destructive=True))
    pd.testing.assert_frame_equal(ds.cleaned_df, before)
    assert not ds.cleaning_result


@pytest.mark.parametrize("query", [
    'WITH ranked AS (SELECT "Customer ID", ROW_NUMBER() OVER (PARTITION BY "Customer ID" ORDER BY amount DESC) AS rn FROM "public"."sales") SELECT * FROM ranked WHERE rn=1;',
    "/* comment */ SELECT 'drop; update', $$hello; delete$$ AS message; -- end",
    'SELECT "delete" FROM "orders" JOIN "customers" USING (id)',
])
def test_complex_read_queries(query):
    assert is_select_only(query)


@pytest.mark.parametrize("query", ["SELECT 1; DROP TABLE x", "SELECT 1;;", "WITH x AS (DELETE FROM sales RETURNING *) SELECT * FROM x", "SELECT * INTO new_table FROM sales"])
def test_unsafe_sql(query):
    assert not is_select_only(query)


def test_confirm_never_allows_stacked_statements():
    with pytest.raises(HTTPException) as exc:
        sql_routes.run_query(SqlQueryRequest(query="DELETE FROM t; DROP TABLE t"), confirm=True)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("code,phrase", [("42P01", "schema-qualified"), ("42703", "column names"), ("42501", "Permission"), ("42601", "syntax"), ("57014", "timed out")])
def test_actionable_sql_errors(code, phrase):
    exc = Exception("password=secret raw query")
    exc.orig = SimpleNamespace(sqlstate=code)
    status, message = sql_routes.query_error(exc)
    assert status == 400 and phrase in message
    assert "secret" not in message


def test_query_preserves_sql_and_bounds_output(monkeypatch):
    conn = MagicMock()
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    monkeypatch.setattr(database, "get_engine", lambda: engine)
    result = conn.execution_options.return_value.exec_driver_sql.return_value
    result.returns_rows = True
    result.fetchmany.return_value = [(1,), (2,), (3,)]
    result.keys.return_value = ["value"]
    query = "WITH t AS (SELECT 1 AS value) SELECT * FROM t"
    response = sql_routes.run_query(SqlQueryRequest(query=query, limit=2, timeout_ms=1000), confirm=False)
    assert response.truncated and len(response.rows) == 2
    result.fetchmany.assert_called_once_with(3)
    conn.exec_driver_sql.assert_called_once_with("SET TRANSACTION READ ONLY")
    conn.execution_options.return_value.exec_driver_sql.assert_called_once_with(query)
    assert conn.execute.call_args.args[1] == {"timeout": "1000"}


def test_disconnected_database(monkeypatch):
    def fail():
        raise RuntimeError("private connection details")
    monkeypatch.setattr(database, "get_engine", fail)
    with pytest.raises(HTTPException) as exc:
        sql_routes.run_query(SqlQueryRequest(query="SELECT 1"), confirm=False)
    assert exc.value.status_code == 503
    assert "private" not in exc.value.detail


def test_identifiers_and_pg_types():
    from backend.services.schema_service import build_create_table_sql
    names = dedupe_identifiers(["a", "a", "a_1", "x"*63, "x"*63])
    assert len(set(names)) == len(names) and max(map(len, names)) <= 63
    assert '"amount" DOUBLE PRECISION' in build_create_table_sql("sales", {"amount": "DOUBLE PRECISION"})


def test_customer_identifier_not_used_as_order_identifier():
    from backend.services.analytics_service import generate_kpis
    kpis = generate_kpis(pd.DataFrame({"client_id": ["A", "A", "B"]}), {"client_id": "identifier"})
    assert {k["label"]: k["value"] for k in kpis} == {"Total Customers": 2}


@pytest.mark.parametrize("features,k,eligible", [([],4,False), (["customer_id"],4,False), (["constant"],4,False), (["amount"],0,False), (["amount"],4,True)])
def test_kmeans_validation(features, k, eligible):
    df = pd.DataFrame({"customer_id": range(20), "constant": [1]*20, "amount": [float(i) if i != 2 else np.nan for i in range(20)]})
    assert kmeans_segments(df, features, k)["eligible"] is eligible


def test_rfm_invalid_transactions():
    df = pd.DataFrame({"client": ["Unknown", "A", "B"], "date": ["2024-01-01", "invalid", "2024-02-01"], "amount": [10, 20, np.nan]})
    assert compute_rfm(df, "client", "date", "amount").empty


def test_restart_restores_audit_and_idempotency(isolated):
    ds = file_service.store_new_dataset("restart.csv", fixture_csv())
    profile_routes.get_profile(ds.dataset_id)
    options = CleaningOptions(run_anomaly_detection=False, confirm_destructive=True)
    applied = cleaning_routes.apply_cleaning(ds.dataset_id, options)
    del file_service.registry._datasets[ds.dataset_id]
    restored = file_service.registry.get(ds.dataset_id)
    assert restored.column_roles["amount"] == "currency_amount"
    assert cleaning_routes.apply_cleaning(ds.dataset_id, options) == applied


def test_cross_origin_writes_blocked(isolated):
    response = isolated.post("/api/sql/query", headers={"Origin": "https://untrusted.example"}, json={"query": "SELECT 1"})
    assert response.status_code == 403


def test_ambiguous_and_ineligible_segmentation(isolated):
    ds = file_service.store_new_dataset("ambiguous.csv", fixture_csv())
    profile_routes.get_profile(ds.dataset_id)
    ds.cleaned_df["revenue"] = ds.cleaned_df["amount"]
    ds.column_roles["revenue"] = "currency_amount"
    result = isolated.get(f"/api/analytics/{ds.dataset_id}/segmentation").json()
    assert not result["rfm"]["eligible"] and "amount" in result["rfm"]["reason"]
    assert isolated.get(f"/api/analytics/{ds.dataset_id}/segmentation?amount_column=amount").json()["rfm"]["eligible"]
    assert isolated.get(f"/api/analytics/{ds.dataset_id}/segmentation?amount_column=missing").status_code == 400


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_upload_to_reports_pipeline(isolated, extension):
    raw = fixture_csv()
    if extension == "xlsx":
        buf = io.BytesIO()
        pd.read_csv(io.BytesIO(raw)).to_excel(buf, index=False)
        raw = buf.getvalue()
    response = isolated.post("/api/upload", files={"file": (f"new name.{extension}", raw)})
    assert response.status_code == 200, response.text
    ident = response.json()["dataset_id"]
    assert isolated.get(f"/api/profile/{ident}").status_code == 200
    options = {"run_anomaly_detection": False, "confirm_destructive": True}
    assert isolated.post(f"/api/cleaning/{ident}/preview", json=options).status_code == 200
    applied = isolated.post(f"/api/cleaning/{ident}/apply", json=options)
    assert applied.status_code == 200, applied.text
    for path in [f"/api/cleaning/{ident}/data-preview", f"/api/analytics/{ident}/eda", f"/api/analytics/{ident}/insights", f"/api/analytics/{ident}/kpis", f"/api/dashboard/{ident}"]:
        result = isolated.get(path)
        assert result.status_code == 200, (path, result.text)
    segments = isolated.get(f"/api/analytics/{ident}/segmentation").json()
    assert segments["rfm"]["eligible"] and segments["kmeans"]["eligible"]
    for kind in ["csv", "xlsx", "powerbi"]:
        export = isolated.get(f"/api/dashboard/{ident}/export/{kind}")
        assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]
        data = pd.read_csv(io.BytesIO(export.content)) if kind == "csv" else pd.read_excel(io.BytesIO(export.content))
        assert len(data) == 40
    assert isolated.get("/api/dashboard/nonexistent/export/powerbi").status_code == 404
    assert isolated.get("/api/dashboard/nonexistent/export/pbids").status_code == 404


@pytest.mark.parametrize("name,content", [("bad.csv", b"\x00binary"), ("bad.xlsx", b"not excel"), ("bad.csv", b"<html>error</html>"), ("bad.exe", b"a,b\n1,2")])
def test_invalid_uploads(isolated, name, content):
    assert isolated.post("/api/upload", files={"file": (name, content)}).status_code == 400
