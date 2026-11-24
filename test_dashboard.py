"""Tests for chart recommendation and dashboard assembly (Sections 26, 27)."""
import numpy as np
import pandas as pd

from backend.services.dashboard_service import build_dashboard
from backend.services.visualization_service import recommend_charts


COLUMN_ROLES = {
    "order_date": "date_time",
    "product_category": "categorical",
    "total_sales": "currency_amount",
    "quantity": "numeric",
    "unit_price": "numeric",
}


def test_recommend_charts_includes_line_for_date_and_numeric():
    charts = recommend_charts(
        COLUMN_ROLES,
        numeric_columns=["total_sales", "quantity", "unit_price"],
        categorical_columns=["product_category"],
        date_columns=["order_date"],
        category_cardinality={"product_category": 3},
    )
    chart_types = [c["chart_type"] for c in charts]
    assert "line" in chart_types
    assert "bar" in chart_types
    assert "scatter" in chart_types
    assert "correlation_heatmap" in chart_types


def test_recommend_charts_suggests_donut_for_low_cardinality_category():
    charts = recommend_charts(
        COLUMN_ROLES,
        numeric_columns=["total_sales"],
        categorical_columns=["product_category"],
        date_columns=[],
        category_cardinality={"product_category": 3},
    )
    assert any(c["chart_type"] == "donut" for c in charts)


def test_recommend_charts_skips_donut_for_high_cardinality_category():
    charts = recommend_charts(
        COLUMN_ROLES,
        numeric_columns=["total_sales"],
        categorical_columns=["product_category"],
        date_columns=[],
        category_cardinality={"product_category": 500},
    )
    assert not any(c["chart_type"] == "donut" for c in charts)


def test_build_dashboard_returns_kpis_and_charts():
    rng = np.random.default_rng(3)
    n = 150
    df = pd.DataFrame({
        "order_date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "product_category": rng.choice(["Electronics", "Clothing"], n),
        "total_sales": np.round(rng.uniform(10, 500, n), 2),
        "quantity": rng.integers(1, 10, n),
        "unit_price": np.round(rng.uniform(5, 100, n), 2),
    })
    dashboard = build_dashboard(df, COLUMN_ROLES, ["total_sales", "quantity", "unit_price"])
    assert "kpis" in dashboard
    assert "charts" in dashboard
    assert "filters" in dashboard
    assert dashboard["filters"]["total_rows"] == n
    assert dashboard["filters"]["filtered_rows"] == n


def test_build_dashboard_with_categorical_filter():
    rng = np.random.default_rng(42)
    n = 100
    df = pd.DataFrame({
        "order_date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "product_category": ["Electronics"] * 40 + ["Clothing"] * 60,
        "total_sales": np.round(rng.uniform(10, 500, n), 2),
        "quantity": rng.integers(1, 10, n),
        "unit_price": np.round(rng.uniform(5, 100, n), 2),
    })
    dashboard = build_dashboard(
        df,
        COLUMN_ROLES,
        ["total_sales", "quantity", "unit_price"],
        filters={"product_category": "Electronics"},
    )
    assert dashboard["filters"]["total_rows"] == 100
    assert dashboard["filters"]["filtered_rows"] == 40
    assert dashboard["filters"]["active_filters"] == {"product_category": "Electronics"}


def test_build_dashboard_with_metric_selection():
    rng = np.random.default_rng(42)
    n = 100
    df = pd.DataFrame({
        "order_date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "product_category": ["Electronics"] * 50 + ["Clothing"] * 50,
        "total_sales": np.round(rng.uniform(10, 500, n), 2),
        "quantity": rng.integers(1, 10, n),
        "unit_price": np.round(rng.uniform(5, 100, n), 2),
    })
    dashboard = build_dashboard(
        df,
        COLUMN_ROLES,
        ["total_sales", "quantity", "unit_price"],
        selected_metric="quantity",
    )
    assert dashboard["filters"]["selected_metric"] == "quantity"
    # Verify first chart title or metric column is quantity
    chart0 = dashboard["charts"][0]
    assert "Quantity" in chart0["title"] or chart0.get("data", {}).get("metric_column") == "quantity"


def test_powerbi_export_generation():
    from backend.services.powerbi_service import generate_powerbi_package, generate_pbids

    rng = np.random.default_rng(42)
    n = 50
    df = pd.DataFrame({
        "order_date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "product_category": ["Electronics"] * 25 + ["Clothing"] * 25,
        "total_sales": np.round(rng.uniform(10, 500, n), 2),
        "quantity": rng.integers(1, 10, n),
    })
    dashboard = build_dashboard(df, COLUMN_ROLES, ["total_sales", "quantity"])
    pkg = generate_powerbi_package("test_ds", df, COLUMN_ROLES, dashboard["charts"], dashboard["kpis"])
    assert isinstance(pkg, bytes)
    assert len(pkg) > 1000

    pbids = generate_pbids("test_ds")
    assert isinstance(pbids, bytes)
    assert b"protocol" in pbids

