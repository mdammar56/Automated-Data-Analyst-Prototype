"""
backend/services/insight_service.py

Automatic Insight Detection (Section 25). Generates plain-language findings
from the data itself — trend changes, top/bottom performers, revenue
concentration, unusual rates and notable correlations — and only proposes a
recommendation when it is directly supported by the data. Correlation
findings are always described without implying causation.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from backend.services.analytics_service import (
    correlation_matrix,
    detected_business_columns,
    time_series_trend,
    top_bottom,
)


def _trend_insight(df: pd.DataFrame, date_col: Optional[str], revenue_col: Optional[str]) -> list[dict[str, Any]]:
    if not date_col or not revenue_col:
        return []
    series = time_series_trend(df, date_col, revenue_col, freq="ME")
    if len(series) < 2:
        return []
    prev, last = series[-2]["value"], series[-1]["value"]
    if prev == 0:
        return []
    change_pct = (last - prev) / abs(prev) * 100
    direction = "increased" if change_pct >= 0 else "decreased"
    return [{
        "type": "trend",
        "title": "Revenue",
        "message": f"Revenue {direction} {abs(round(change_pct, 1))}% during the most recent period compared with the prior period.",
    }]


def _top_category_insight(df: pd.DataFrame, category_col: Optional[str], revenue_col: Optional[str]) -> list[dict[str, Any]]:
    if not category_col or not revenue_col:
        return []
    result = top_bottom(df, category_col, revenue_col, n=1)
    if not result["top"]:
        return []
    top_name, top_value = next(iter(result["top"].items()))
    return [{
        "type": "top_performer",
        "title": "Category",
        "message": f"'{top_name}' generated the highest {revenue_col.replace('_', ' ')} ({top_value:,.2f}).",
    }]


def _concentration_insight(df: pd.DataFrame, customer_col: Optional[str], revenue_col: Optional[str]) -> list[dict[str, Any]]:
    if not customer_col or not revenue_col:
        return []
    spend = pd.to_numeric(df[revenue_col], errors="coerce").groupby(df[customer_col]).sum().sort_values(ascending=False)
    total = spend.sum()
    if total == 0 or len(spend) < 10:
        return []
    top_decile_n = max(1, int(len(spend) * 0.1))
    top_share = spend.head(top_decile_n).sum() / total * 100
    return [{
        "type": "concentration",
        "title": "Customer Concentration",
        "message": f"The top 10% of customers contribute {round(top_share, 1)}% of total {revenue_col.replace('_', ' ')}.",
    }]


def _rate_anomaly_insight(df: pd.DataFrame, category_col: Optional[str], rate_col: Optional[str]) -> list[dict[str, Any]]:
    if not category_col or not rate_col:
        return []
    series = pd.to_numeric(df[rate_col], errors="coerce")
    if series.dropna().empty:
        return []
    grouped = series.groupby(df[category_col]).mean()
    overall_mean, overall_std = series.mean(), series.std(ddof=0)
    if overall_std == 0 or pd.isna(overall_std):
        return []
    flagged = grouped[(grouped - overall_mean).abs() > 2 * overall_std]
    insights = []
    for name, value in flagged.items():
        insights.append({
            "type": "rate_anomaly",
            "title": "Anomaly",
            "message": f"'{name}' has an unusually {'high' if value > overall_mean else 'low'} average {rate_col.replace('_', ' ')} ({value:.2f}).",
        })
    return insights[:3]


def _correlation_insight(df: pd.DataFrame, numeric_columns: list[str]) -> list[dict[str, Any]]:
    corr = correlation_matrix(df, numeric_columns)
    findings = []
    seen = set()
    for col_a, row in corr.items():
        for col_b, value in row.items():
            if col_a == col_b:
                continue
            pair = tuple(sorted((col_a, col_b)))
            if pair in seen:
                continue
            seen.add(pair)
            if abs(value) >= 0.7:
                findings.append({
                    "type": "correlation",
                    "title": "Correlation",
                    "message": (
                        f"'{col_a}' and '{col_b}' show a strong "
                        f"{'positive' if value > 0 else 'negative'} correlation ({value}). "
                        "Correlation does not imply causation."
                    ),
                })
    return findings[:3]


def generate_insights(df: pd.DataFrame, column_roles: dict[str, str], numeric_columns: list[str]) -> list[dict[str, Any]]:
    cols = detected_business_columns(column_roles)
    insights: list[dict[str, Any]] = []

    insights += _trend_insight(df, cols["date_column"], cols["revenue_column"])
    insights += _top_category_insight(df, cols["category_column"], cols["revenue_column"])
    insights += _concentration_insight(df, cols["customer_id_column"], cols["revenue_column"])
    insights += _rate_anomaly_insight(df, cols["category_column"], cols["return_column"] or cols["discount_column"])
    insights += _correlation_insight(df, numeric_columns)

    recommendations = []
    for insight in insights:
        if insight["type"] == "rate_anomaly":
            recommendations.append({
                "type": "recommendation",
                "title": "Recommendation",
                "message": f"Investigate the underlying cause behind: {insight['message']}",
            })
        elif insight["type"] == "concentration":
            recommendations.append({
                "type": "recommendation",
                "title": "Recommendation",
                "message": "Consider a loyalty or retention program targeted at top-spending customers.",
            })

    if not insights:
        insights.append({
            "type": "info",
            "title": "Insights",
            "message": "Not enough business-relevant columns (revenue, date, category, customer) were detected to generate automatic insights.",
        })

    return insights + recommendations
