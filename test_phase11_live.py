"""Opt-in actual local dataset import and analytic verification; all DB writes roll back."""
import os
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
import pandas as pd
import pytest
from backend import database
from backend.config import BASE_DIR
from backend.services.file_service import registry
from backend.api.profile_routes import get_profile
from backend.services.database_service import load_dataframe_to_postgres
from backend.api.database_routes import database_metadata

@pytest.mark.skipif(os.getenv('RUN_POSTGRES_TESTS') != '1', reason='Live database check')
def test_actual_uploaded_dataset_import_and_complex_sql(monkeypatch):
    paths = list((BASE_DIR / 'data/uploads').glob('*customer_shopping_behavior.csv'))
    if not paths:
        pytest.skip('Actual customer-shopping upload is unavailable')
    dataset_id = paths[0].name.split('_',1)[0]
    get_profile(dataset_id)
    ds = registry.get(dataset_id)
    frame = ds.cleaned_df
    table = 'phase11_verify_' + uuid.uuid4().hex
    engine = database.get_engine()
    with engine.connect() as conn:
        transaction = conn.begin()
        @contextmanager
        def begin(): yield conn
        monkeypatch.setattr(database, 'get_engine', lambda: SimpleNamespace(begin=begin))
        try:
            result = load_dataframe_to_postgres(frame, table, ds.column_dtypes)
            assert result['rows_loaded'] == len(frame)
            assert any(t['reference'] == f'"public"."{table}"' for t in database_metadata()['tables'])
            rows = conn.exec_driver_sql(f'''WITH ranked AS (
              SELECT category, purchase_amount_usd,
              ROW_NUMBER() OVER(PARTITION BY category ORDER BY purchase_amount_usd DESC) AS rn
              FROM "public"."{table}"
            ) SELECT category, SUM(purchase_amount_usd) FROM ranked
              WHERE rn<=3 GROUP BY category ORDER BY category''').all()
            expected = frame.groupby('category')['purchase_amount_usd'].apply(lambda s:s.nlargest(3).sum()).to_dict()
            assert dict(rows) == expected
        finally:
            transaction.rollback()
