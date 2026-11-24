"""
backend/services/visualization_service.py

Automatic Visualization Recommendation (Section 26). Maps detected column
patterns to chart types, matching the recommendation table in the blueprint:
date+numeric -> line, category+numeric -> bar, top-N -> horizontal bar,
limited categories -> donut, two numerics -> scatter, single numeric ->
histogram/box, many numerics -> correlation heatmap.
"""
from __future__ import annotations

from typing import Any

MAX_DONUT_CATEGORIES = 6


def recommend_charts(column_roles: dict[str, str], numeric_columns: list[str],
                      categorical_columns: list[str], date_columns: list[str],
                      category_cardinality: dict[str, int]) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []

    for date_col in date_columns:
        for num_col in numeric_columns[:3]:
            charts.append({
                "chart_type": "line",
                "x": date_col, "y": num_col,
                "reason": "Date + numeric metric is best shown as a trend line.",
            })

    for cat_col in categorical_columns:
        for num_col in numeric_columns[:2]:
            cardinality = category_cardinality.get(cat_col, 0)
            if cardinality and cardinality <= MAX_DONUT_CATEGORIES:
                charts.append({
                    "chart_type": "donut",
                    "category": cat_col, "value": num_col,
                    "reason": "Limited category composition suits a donut chart.",
                })
            charts.append({
                "chart_type": "bar",
                "x": cat_col, "y": num_col,
                "reason": "Category + numeric metric is best compared as a bar chart.",
            })
            charts.append({
                "chart_type": "horizontal_bar_top_n",
                "x": cat_col, "y": num_col, "n": 10,
                "reason": "Top-N products/categories read more clearly as a horizontal bar chart.",
            })

    if len(numeric_columns) >= 2:
        charts.append({
            "chart_type": "scatter",
            "x": numeric_columns[0], "y": numeric_columns[1],
            "reason": "Relationship between two numeric variables suits a scatter plot.",
        })

    for num_col in numeric_columns[:3]:
        charts.append({
            "chart_type": "histogram",
            "x": num_col,
            "reason": "Distribution of a single numeric variable suits a histogram/box plot.",
        })

    if len(numeric_columns) >= 3:
        charts.append({
            "chart_type": "correlation_heatmap",
            "columns": numeric_columns,
            "reason": "Several numeric variables suit a correlation heatmap.",
        })

    return charts
