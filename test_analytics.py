"""Tests for KPI generation, insight detection and segmentation (Sections 24, 25, 28)."""
import numpy as np
import pandas as pd

from backend.services.analytics_service import detected_business_columns, generate_kpis
from backend.services.insight_service import generate_insights
from backend.ml.segmentation import compute_rfm, rfm_eligible, score_rfm, kmeans_segments


def _sample_df(n=200):
    rng = np.random.default_rng(1)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "order_id": [f"ORD{i}" for i in range(n)],
        "order_date": rng.choice(dates, n),
        "customer_id": [f"CUST{i % 40}" for i in rng.integers(0, 40, n)],
        "product_category": rng.choice(["Electronics", "Clothing", "Toys"], n),
        "total_sales": np.round(rng.uniform(10, 500, n), 2),
        "quantity": rng.integers(1, 10, n),
    })


COLUMN_ROLES = {
    "order_id": "identifier",
    "order_date": "date_time",
    "customer_id": "identifier",
    "product_category": "categorical",
    "total_sales": "currency_amount",
    "quantity": "numeric",
}


def test_detected_business_columns_finds_revenue_and_customer():
    cols = detected_business_columns(COLUMN_ROLES)
    assert cols["revenue_column"] == "total_sales"
    assert cols["customer_id_column"] == "customer_id"
    assert cols["date_column"] == "order_date"


def test_generate_kpis_includes_total_revenue_and_orders():
    df = _sample_df()
    kpis = generate_kpis(df, COLUMN_ROLES)
    labels = [k["label"] for k in kpis]
    assert "Total Revenue" in labels
    assert "Total Orders" in labels
    assert "Total Customers" in labels


def test_generate_kpis_falls_back_to_row_count_without_business_columns():
    df = pd.DataFrame({"free_text": ["a", "b", "c"]})
    kpis = generate_kpis(df, {"free_text": "text"})
    assert kpis[0]["label"] == "Total Rows"
    assert kpis[0]["value"] == 3


def test_generate_insights_returns_list_without_crashing():
    df = _sample_df()
    insights = generate_insights(df, COLUMN_ROLES, ["total_sales", "quantity"])
    assert isinstance(insights, list)
    assert len(insights) > 0


def test_generate_insights_handles_dataset_with_no_business_columns():
    df = pd.DataFrame({"a": [1, 2, 3]})
    insights = generate_insights(df, {"a": "numeric"}, ["a"])
    assert any(i["type"] == "info" for i in insights)


def test_rfm_eligible_requires_all_three_columns():
    assert rfm_eligible("customer_id", "order_date", "total_sales") is True
    assert rfm_eligible(None, "order_date", "total_sales") is False


def test_compute_and_score_rfm():
    df = _sample_df(n=300)
    rfm = compute_rfm(df, "customer_id", "order_date", "total_sales")
    assert set(rfm.columns) >= {"customer_id", "recency_days", "frequency", "monetary"}
    scored = score_rfm(rfm)
    assert "segment" in scored.columns
    assert scored["segment"].nunique() >= 1


def test_kmeans_segments_eligible_with_enough_rows():
    df = _sample_df(n=200)
    result = kmeans_segments(df, ["total_sales", "quantity"], n_clusters=3)
    assert result["eligible"] is True
    assert "cluster_sizes" in result


def test_kmeans_segments_not_eligible_with_too_few_rows():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    result = kmeans_segments(df, ["a", "b"], n_clusters=4)
    assert result["eligible"] is False


def test_numeric_distributions_returns_stats_and_values():
    from backend.services.analytics_service import numeric_distributions

    df = pd.DataFrame({"col_a": [10, 20, 30, 40, 50, np.nan], "col_b": ["invalid", "100", "200", "300", None, "400"]})
    dist = numeric_distributions(df, ["col_a", "col_b", "non_existent"])
    assert "col_a" in dist
    assert "col_b" in dist
    assert "non_existent" not in dist
    assert dist["col_a"]["min"] == 10.0
    assert dist["col_a"]["max"] == 50.0
    assert dist["col_a"]["mean"] == 30.0
    assert dist["col_a"]["count"] == 5
    assert len(dist["col_a"]["values"]) == 5
    assert "iqr" in dist["col_a"]
    assert "skew" in dist["col_a"]


def test_categorical_frequencies_returns_counts_and_totals():
    from backend.services.analytics_service import categorical_frequencies

    df = pd.DataFrame({"category": ["A", "B", "A", "C", "A", "B", None]})
    freq = categorical_frequencies(df, ["category", "missing_col"])
    assert "category" in freq
    assert "missing_col" not in freq
    assert freq["category"]["total"] == 6
    assert freq["category"]["unique_count"] == 3
    assert freq["category"]["counts"]["A"] == 3
    assert freq["category"]["counts"]["B"] == 2


def test_correlation_matrix_computes_corr_and_handles_single_col():
    from backend.services.analytics_service import correlation_matrix

    df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10], "z": [5, 4, 3, 2, 1]})
    corr = correlation_matrix(df, ["x", "y", "z"])
    assert len(corr) == 3
    assert corr["x"]["y"] == 1.0
    assert corr["x"]["z"] == -1.0

    single_corr = correlation_matrix(df, ["x"])
    assert single_corr == {}
