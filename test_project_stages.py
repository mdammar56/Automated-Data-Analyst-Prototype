"""End-to-end stage regressions with isolated project storage."""
import io
from types import SimpleNamespace
from unittest.mock import MagicMock
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import database, security
from backend.services import file_service, project_service, ai_service
from tests.test_stabilization import isolated, fixture_csv


def upload(client, raw=None):
    response = client.post('/api/upload', files={'file': ('stages.csv', raw or fixture_csv())})
    assert response.status_code == 200
    key = response.json()['dataset_id']
    assert client.get(f'/api/profile/{key}').status_code == 200
    return key


def test_cleaning_confirmation_undo_restart_and_dictionary(isolated):
    key = upload(isolated)
    original = file_service.registry.get(key).cleaned_df.copy()
    options = {'run_anomaly_detection': False}
    assert isolated.post(f'/api/cleaning/{key}/apply', json=options).status_code == 409
    assert len(file_service.registry.get(key).cleaned_df) == 41
    response = isolated.post(f'/api/cleaning/{key}/apply', json={**options, 'confirm_destructive': True})
    assert response.status_code == 200, response.text
    changed = response.json()['audit_log'][-1]['detail']
    assert changed['rows_removed'] == 1 and changed['values_changed'] >= 1
    file_service.registry._datasets.clear()
    assert len(file_service.registry.get(key).cleaned_df) == 40
    assert isolated.post(f'/api/projects/{key}/undo').status_code == 200
    pd.testing.assert_frame_equal(file_service.registry.get(key).cleaned_df, original)
    response = isolated.put(f'/api/projects/{key}/dictionary', json={'column':'client_id','role':'customer_id','description':'Buyer','unit':''})
    assert response.status_code == 200
    file_service.registry._datasets.clear()
    doc = isolated.get(f'/api/projects/{key}').json()
    assert next(d for d in doc['dictionary'] if d['column']=='client_id')['role']=='customer_id'
    assert doc['version'] == 4
    assert isolated.post(f'/api/projects/{key}/undo').status_code == 200
    assert file_service.registry.get(key).column_roles['client_id'] == 'identifier'


def test_empty_filters_chart_exports_and_saved_settings(isolated):
    key = upload(isolated)
    filters = {'amount': {'kind':'numeric','min':10000}}
    response = isolated.get(f'/api/dashboard/{key}', params={'filters': __import__('json').dumps(filters)})
    assert response.status_code == 200, response.text
    dashboard = response.json()
    assert dashboard['filters']['filtered_rows'] == 0
    assert next(k for k in dashboard['kpis'] if k['label']=='Total Revenue')['value'] == 0
    exported = isolated.get(f'/api/dashboard/{key}/export/csv?filtered=true')
    assert pd.read_csv(io.BytesIO(exported.content)).empty
    file_service.registry._datasets.clear()
    assert isolated.get(f'/api/projects/{key}').json()['dashboard']['filters'] == filters
    spec = {'x':'client_id','y':'amount','type':'bar','aggregation':'sum','filters':{}}
    chart = isolated.post(f'/api/projects/{key}/chart', json=spec)
    assert chart.status_code == 200, chart.text
    assert sum(chart.json()['data'][0]['y']) == pytest.approx(file_service.registry.get(key).cleaned_df.amount.sum())
    assert isolated.post(f'/api/projects/{key}/chart', json={**spec,'y':'client_id'}).status_code == 400
    assert isolated.get(f'/api/dashboard/{key}', params={'filters':'[]'}).status_code == 400


def test_pdf_comparison_and_formula_safe_exports(isolated):
    key = upload(isolated, b'Group,Amount,Notes\nA,0,=1+1\nB,0,@cmd\n')
    other = upload(isolated, b'Group,Amount\nA,10\nB,20\n')
    result = isolated.post(f'/api/projects/{key}/compare', json={'other_id':other,'column':'amount','other_column':'amount','confirm_units':True})
    assert result.status_code == 200, result.text
    assert result.json()['absolute_change'] == 30
    assert result.json()['percentage_change'] is None
    assert isolated.post(f'/api/projects/{key}/compare', json={'other_id':other,'column':'amount','other_column':'amount'}).status_code == 400
    pdf = isolated.get(f'/api/projects/{key}/report.pdf')
    assert pdf.status_code == 200, pdf.text[:100] if pdf.status_code != 200 else ''
    assert pdf.content.startswith(b'%PDF') and len(pdf.content) > 2000
    history = isolated.get(f'/api/projects/{key}/history').json()
    saved = next(h for h in history if h['kind']=='report')
    assert isolated.get(f"/api/projects/{key}/reports/{saved['filename']}").content == pdf.content
    workbook = isolated.get(f'/api/dashboard/{key}/export/xlsx')
    excel = pd.ExcelFile(io.BytesIO(workbook.content))
    assert 'data_dictionary' in excel.sheet_names
    assert pd.read_excel(excel)['notes'].iloc[0].startswith("'=")


def test_grounded_context_and_stale_history(isolated, monkeypatch):
    monkeypatch.setattr(ai_service, 'is_ai_enabled', lambda: False)
    key = upload(isolated)
    response = isolated.post(f'/api/projects/{key}/ask', json={'question':'Explain cleaning quality'})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer['used_ai'] is False and '[quality]' in answer['answer']
    assert answer['evidence']
    isolated.put(f'/api/projects/{key}/dictionary', json={'column':'notes','role':'text'})
    history = isolated.get(f'/api/projects/{key}/history').json()
    assert history[0]['stale'] is True
    monkeypatch.setattr(ai_service, 'is_ai_enabled', lambda: True)
    monkeypatch.setattr(ai_service, '_get_client_and_model', lambda:(object(),'test'))
    monkeypatch.setattr(ai_service, '_generate_text', lambda *args:'["invented revenue 999999"]')
    response = isolated.post(f'/api/projects/{key}/ask', json={'question':'Revenue?'})
    assert '999999' not in response.json()['answer']


def test_auth_covers_pages_exports_and_production_guard(isolated, monkeypatch):
    settings = SimpleNamespace(app_username='analyst',app_password='test-password-for-tests',app_env='production',database_query_role='reader')
    monkeypatch.setattr(security,'get_settings',lambda:settings)
    security.validate_deployment()
    for path in ['/', '/api/projects', '/api/projects/anything/report.pdf', '/health']:
        assert isolated.get(path).status_code == 401
    assert isolated.get('/api/projects', auth=('analyst','wrong')).status_code == 401
    assert isolated.get('/api/projects', auth=('analyst','test-password-for-tests')).status_code == 200
    settings.app_password=''
    with pytest.raises(RuntimeError): security.validate_deployment()


def test_query_history_persists(isolated, monkeypatch):
    key = upload(isolated)
    engine, conn = MagicMock(), MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    result = conn.execution_options.return_value.exec_driver_sql.return_value
    result.returns_rows = True
    result.fetchmany.return_value = [(12,), (15,)]
    result.keys.return_value = ['amount']
    monkeypatch.setattr(database,'get_engine',lambda:engine)
    response = isolated.post('/api/sql/query', json={'dataset_id':key,'query':'SELECT amount FROM example','limit':1})
    assert response.status_code == 200, response.text
    file_service.registry._datasets.clear()
    history = isolated.get(f'/api/projects/{key}/history').json()
    assert history[0]['query'] == 'SELECT amount FROM example'
    assert history[0]['truncated'] and history[0]['row_count'] == 1
