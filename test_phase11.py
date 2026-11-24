"""Phase 1.1 focused regressions; datasets below are explicit test fixtures."""
import io
from types import SimpleNamespace
from unittest.mock import MagicMock
import pandas as pd
import pytest
from backend.config import Settings, BASE_DIR
from backend.services import ai_service, file_service
from backend.api import database_routes, sql_routes
from backend.schemas import SqlQueryRequest
from backend.ml.segmentation import compute_rfm, kmeans_segments
from tests.test_stabilization import isolated, fixture_csv


def test_settings_absolute_env_path_and_groq(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GROQ_API_KEY', 'test-only-key')
    settings = Settings(_env_file=None, gemini_api_key='')
    assert settings.ai_enabled
    assert Settings.model_config['env_file'] == str(BASE_DIR / '.env')
    monkeypatch.setattr(ai_service, 'get_settings', lambda: settings)
    import groq
    client = MagicMock()
    monkeypatch.setattr(groq, 'Groq', client)
    ai_service._get_client_and_model()
    assert client.call_args.kwargs['api_key'] == 'test-only-key'


@pytest.mark.parametrize('code,phrase', [(401,'authentication'), (404,'model'), (429,'rate limit'), (500,'unavailable')])
def test_provider_errors_never_echo_secrets(monkeypatch, code, phrase):
    monkeypatch.setattr(ai_service, 'is_ai_enabled', lambda: True)
    monkeypatch.setattr(ai_service, '_get_client_and_model', lambda: (object(), 'test'))
    def fail(*args):
        exc = RuntimeError('private-test-secret')
        exc.status_code = code
        raise exc
    monkeypatch.setattr(ai_service, '_generate_text', fail)
    result = ai_service.generate_sql_from_question('Total?', 'sales', {})
    assert phrase in result['explanation']
    assert 'private-test-secret' not in result['explanation']


def test_initialized_key_is_not_reported_as_missing(monkeypatch):
    monkeypatch.setattr(ai_service, 'is_ai_enabled', lambda: True)
    monkeypatch.setattr(ai_service, '_get_client_and_model', lambda: (None, None))
    assert 'initialization failed' in ai_service.generate_sql_from_question('Total?', 'sales', {})['explanation']


def test_rfm_numeric_dates_and_duplicate_mappings():
    frame = pd.DataFrame({'customer': ['A','B'], 'date':[25,32], 'amount':[5,6]})
    assert compute_rfm(frame, 'customer', 'date', 'amount').empty
    assert compute_rfm(frame, 'customer', 'amount', 'amount').empty


def test_manual_rfm_mapping_validation(isolated):
    ds = file_service.store_new_dataset('fixture.csv', fixture_csv())
    path = f'/api/analytics/{ds.dataset_id}/segmentation'
    response = isolated.get(path, params={'customer_column':'client_id','date_column':'amount','amount_column':'amount'})
    assert response.status_code == 400
    result = isolated.get(path, params={'customer_column':'client_id','date_column':'invoice_date','amount_column':'amount'}).json()
    assert result['rfm']['eligible']
    assert all(1 <= r['r_score'] <= 4 for r in result['rfm']['sample'])


def test_kmeans_scatter_and_missing_values():
    frame = pd.DataFrame({'amount':range(30), 'quantity':[i%7 for i in range(30)]})
    frame.loc[2,'quantity'] = float('nan')
    result = kmeans_segments(frame, ['amount','quantity'])
    assert result['eligible'] and sum(result['cluster_sizes'].values()) == 30
    assert len(result['scatter']['points']) == 30
    assert all(pd.notna(p['quantity']) for p in result['scatter']['points'])
    assert kmeans_segments(frame, ['amount'])['scatter'] is None


def test_metadata_quotes_identifiers(monkeypatch):
    conn = MagicMock()
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    conn.execute.return_value.one.return_value = ('analytics', 'public', 'public')
    conn.execute.return_value.all.return_value = [('public', 'Sales "2026"', 'Total Amount', 'numeric')]
    conn.execute.return_value.scalars.return_value = ['public']
    monkeypatch.setattr(database_routes.db, 'get_engine', lambda: engine)
    result = database_routes.database_metadata()
    assert result['tables'][0]['reference'] == '"public"."Sales ""2026"""'
    assert result['tables'][0]['columns'][0]['reference'] == '"Total Amount"'


def test_missing_table_suggestions(monkeypatch):
    from fastapi import HTTPException
    exc = RuntimeError('private database details')
    exc.orig = SimpleNamespace(sqlstate='42P01')
    def fail(): raise exc
    monkeypatch.setattr(sql_routes.db, 'get_engine', fail)
    monkeypatch.setattr(database_routes, 'database_metadata', lambda: {'tables':[{'reference':'"public"."sales_data"'}]})
    with pytest.raises(HTTPException) as caught:
        sql_routes.run_query(SqlQueryRequest(query='SELECT * FROM absent'), confirm=False)
    assert '"public"."sales_data"' in caught.value.detail
    assert 'private' not in caught.value.detail


def test_powerbi_workbook_headers_and_values(isolated):
    ds = file_service.store_new_dataset('fixture.csv', fixture_csv())
    isolated.get(f'/api/profile/{ds.dataset_id}')
    response = isolated.get(f'/api/dashboard/{ds.dataset_id}/export/powerbi')
    assert response.status_code == 200
    assert '.xlsx' in response.headers['content-disposition']
    assert 'spreadsheetml' in response.headers['content-type']
    workbook = pd.read_excel(io.BytesIO(response.content))
    assert len(workbook) == 41 and 'client_id' in workbook.columns

def test_ask_endpoint_safe_query_and_error(isolated, monkeypatch):
    monkeypatch.setattr(database_routes, "database_metadata", lambda: {"tables": [{"reference": "sales", "columns": []}]})
    from backend.api import ai_routes
    monkeypatch.setattr(ai_service, 'is_ai_enabled', lambda: True)
    monkeypatch.setattr(ai_service, 'generate_sql_from_question', lambda *args: {'sql':'SELECT SUM(amount) FROM sales','explanation':None})
    monkeypatch.setattr(ai_service, 'explain_result_in_natural_language', lambda *args: 'Total is 12.')
    engine, conn = MagicMock(), MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    result = conn.execution_options.return_value.exec_driver_sql.return_value
    result.fetchmany.return_value = [(12,)]
    result.keys.return_value = ['sum']
    monkeypatch.setattr(ai_routes.db, 'get_engine', lambda: engine)
    response = isolated.post('/api/ai/ask', json={'question':'Total amount?', 'table_name':'sales'})
    assert response.status_code == 200 and '[[12]]' in response.json()['answer']
    assert conn.exec_driver_sql.call_args_list[0].args == ('SET TRANSACTION READ ONLY',)
    monkeypatch.setattr(ai_service, 'generate_sql_from_question', lambda *args: {'sql':'DELETE FROM sales','explanation':None})
    response = isolated.post('/api/ai/ask', json={'question':'Total?', 'table_name':'sales'})
    assert 'blocked' in response.json()['answer']
