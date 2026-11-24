"""
backend/services/dashboard_service.py

Interactive Dashboard Generator (Section 27). Assembles KPI cards, chart
specs (with underlying data payloads for Plotly), and available filters from
the detected schema and analysis results. This dashboard is never hard-coded
to a single dataset — every element is derived from column-role detection.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.services.analytics_service import (
    detected_business_columns,
    generate_kpis,
    time_series_trend,
    top_bottom,
)
from backend.services.visualization_service import recommend_charts


def build_dashboard(
    df: pd.DataFrame,
    column_roles: dict[str, str],
    numeric_columns: list[str],
    filters: dict[str, str] | None = None,
    selected_metric: str | None = None,
) -> dict[str, Any]:
    cols = detected_business_columns(column_roles)
    categorical_columns = [c for c, r in column_roles.items() if r == "categorical"]
    date_columns = [c for c, r in column_roles.items() if r == "date_time"]
    cardinality = {c: int(df[c].nunique(dropna=True)) for c in categorical_columns}

    total_rows = int(len(df))
    active_filters: dict[str, str] = {}
    df_filtered = df.copy()

    from backend.services.exploration_service import apply_filters
    df_filtered = apply_filters(df, filters)
    active_filters = filters or {}

    filtered_rows = int(len(df_filtered))

    # Determine primary metric
    if selected_metric and selected_metric in numeric_columns:
        primary_metric = selected_metric
    else:
        primary_metric = cols["revenue_column"] or (numeric_columns[0] if numeric_columns else None)

    kpis = generate_kpis(df_filtered, column_roles)
    ordered_numerics = (
        [primary_metric] + [c for c in numeric_columns if c != primary_metric]
        if primary_metric
        else numeric_columns
    )
    chart_specs = recommend_charts(column_roles, ordered_numerics, categorical_columns, date_columns, cardinality)

    charts_with_data: list[dict[str, Any]] = []

    for spec in chart_specs[:8]:
        chart_type = spec["chart_type"]
        data_payload: dict[str, Any] = {}
        title = spec.get("title")

        if chart_type == "line" and primary_metric:
            metric_col = primary_metric if selected_metric else (spec.get("y") or primary_metric)
            if not title:
                title = f"Trend: {metric_col.replace('_', ' ').title()} over {spec['x'].replace('_', ' ').title()}"
            series = time_series_trend(df_filtered, spec["x"], metric_col) if not df_filtered.empty else []
            data_payload = {"series": series, "x_column": spec["x"], "metric_column": metric_col}

        elif chart_type in ("bar", "horizontal_bar_top_n") and primary_metric:
            category_col = spec.get("x") or spec.get("category")
            metric_col = primary_metric if selected_metric else (spec.get("y") or primary_metric)
            if not title:
                prefix = "Top 10" if chart_type == "horizontal_bar_top_n" else "Distribution of"
                title = f"{prefix} {category_col.replace('_', ' ').title()} by {metric_col.replace('_', ' ').title()}"
            if not df_filtered.empty and category_col in df_filtered.columns:
                result = top_bottom(df_filtered, category_col, metric_col, n=10)
                data_payload = {"top": result["top"], "category_column": category_col, "metric_column": metric_col}

        elif chart_type == "donut" and primary_metric:
            category_col = spec.get("category") or spec.get("x")
            metric_col = primary_metric if selected_metric else (spec.get("value") or spec.get("y") or primary_metric)
            if not title:
                title = f"{category_col.replace('_', ' ').title()} Share ({metric_col.replace('_', ' ').title()})"
            if not df_filtered.empty and category_col in df_filtered.columns:
                result = top_bottom(df_filtered, category_col, metric_col, n=6)
                data_payload = {"top": result["top"], "category_column": category_col, "metric_column": metric_col}

        elif chart_type == "histogram":
            metric_col = primary_metric if selected_metric else spec["x"]
            if not title:
                title = f"Histogram of {metric_col.replace('_', ' ').title()}"
            if not df_filtered.empty and metric_col in df_filtered.columns:
                series = pd.to_numeric(df_filtered[metric_col], errors="coerce").dropna()
                data_payload = {"values": series.round(2).tolist()[:2000], "metric_column": metric_col}

        elif chart_type == "box":
            metric_col = primary_metric if selected_metric else (spec.get("y") or spec.get("x") or primary_metric)
            if not title:
                title = f"Box Plot of {metric_col.replace('_', ' ').title()}"
            if not df_filtered.empty and metric_col in df_filtered.columns:
                series = pd.to_numeric(df_filtered[metric_col], errors="coerce").dropna()
                data_payload = {"values": series.round(2).tolist()[:2000], "metric_column": metric_col}

        elif chart_type == "scatter":
            x_col = spec["x"]
            y_col = spec["y"]
            if not title:
                title = f"{x_col.replace('_', ' ').title()} vs {y_col.replace('_', ' ').title()}"
            if not df_filtered.empty and x_col in df_filtered.columns and y_col in df_filtered.columns:
                sub = df_filtered[[x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()
                data_payload = {
                    "x": sub[x_col].tolist()[:2000],
                    "y": sub[y_col].tolist()[:2000],
                    "x_column": x_col,
                    "y_column": y_col,
                }

        elif chart_type == "correlation_heatmap":
            if not title:
                title = "Correlation Heatmap"
            if not df_filtered.empty:
                from backend.services.analytics_service import correlation_matrix
                data_payload = {"matrix": correlation_matrix(df_filtered, spec["columns"])}

        charts_with_data.append({**spec, "title": title, "data": data_payload})

    filters_dict = {
        "date_columns": date_columns,
        "categorical_filters": {
            c: sorted(df[c].dropna().astype(str).unique().tolist())[:50]
            for c in categorical_columns[:6]
        },
        "active_filters": active_filters,
        "available_metrics": numeric_columns,
        "selected_metric": primary_metric,
        "total_rows": total_rows,
        "filtered_rows": filtered_rows,
    }

    return {
        "kpis": kpis,
        "charts": charts_with_data,
        "filters": filters_dict,
        "detected_columns": cols,
    }
