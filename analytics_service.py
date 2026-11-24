"""
backend/services/analytics_service.py

Automated EDA and statistical analysis (Section 23) plus dynamic KPI
generation (Section 24). KPIs are selected from detected business concepts
(revenue-like, quantity-like, customer-like, date-like columns) rather than
hard-coded to any single dataset's schema.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd


def numeric_distributions(df: pd.DataFrame, numeric_columns: list[str]) -> dict[str, Any]:
    result = {}
    for col in numeric_columns:
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        p25 = float(np.percentile(series, 25))
        p75 = float(np.percentile(series, 75))
        skew_val = float(series.skew()) if len(series) > 2 else 0.0
        if np.isnan(skew_val):
            skew_val = 0.0
        sample_vals = series.sample(5000, random_state=42).tolist() if len(series) > 5000 else series.tolist()
        result[col] = {
            "min": round(float(series.min()), 4),
            "max": round(float(series.max()), 4),
            "mean": round(float(series.mean()), 4),
            "median": round(float(series.median()), 4),
            "std": round(float(series.std(ddof=0)), 4),
            "p25": round(p25, 4),
            "p75": round(p75, 4),
            "iqr": round(p75 - p25, 4),
            "skew": round(skew_val, 4),
            "count": int(len(series)),
            "values": [round(float(v), 4) for v in sample_vals],
        }
    return result


def categorical_frequencies(df: pd.DataFrame, categorical_columns: list[str], top_n: int = 10) -> dict[str, Any]:
    result = {}
    for col in categorical_columns:
        if col not in df.columns:
            continue
        series = df[col].dropna().astype(str)
        if series.empty:
            continue
        counts = series.value_counts().head(top_n).to_dict()
        result[col] = {
            "counts": counts,
            "total": int(len(series)),
            "unique_count": int(series.nunique()),
        }
    return result


def correlation_matrix(df: pd.DataFrame, numeric_columns: list[str]) -> dict[str, dict[str, float]]:
    valid_numeric = [c for c in numeric_columns if c in df.columns]
    if len(valid_numeric) < 2:
        return {}
    numeric_df = df[valid_numeric].apply(pd.to_numeric, errors="coerce")
    corr = numeric_df.corr(numeric_only=True).round(3).fillna(0.0)
    return corr.to_dict()


def time_series_trend(df: pd.DataFrame, date_col: str, metric_col: str, freq: str = "ME") -> list[dict[str, Any]]:
    working = df[[date_col, metric_col]].copy()
    working[date_col] = pd.to_datetime(working[date_col], errors="coerce")
    working[metric_col] = pd.to_numeric(working[metric_col], errors="coerce")
    working = working.dropna()
    if working.empty:
        return []
    grouped = working.set_index(date_col).resample(freq)[metric_col].sum()
    return [{"period": str(idx.date()), "value": float(val)} for idx, val in grouped.items()]


def top_bottom(df: pd.DataFrame, group_col: str, metric_col: str, n: int = 10) -> dict[str, Any]:
    working = df[[group_col, metric_col]].copy()
    working[metric_col] = pd.to_numeric(working[metric_col], errors="coerce")
    grouped = working.groupby(group_col)[metric_col].sum().sort_values(ascending=False)
    return {
        "top": grouped.head(n).to_dict(),
        "bottom": grouped.tail(n).to_dict(),
    }


def customer_purchase_patterns(df: pd.DataFrame, customer_col: str, amount_col: str) -> dict[str, Any]:
    working = df[[customer_col, amount_col]].copy()
    working[amount_col] = pd.to_numeric(working[amount_col], errors="coerce")
    grouped = working.groupby(customer_col)[amount_col].agg(["count", "sum", "mean"]).rename(
        columns={"count": "purchase_frequency", "sum": "total_spend", "mean": "avg_spend"}
    )
    return {
        "avg_purchase_frequency": float(grouped["purchase_frequency"].mean()),
        "avg_total_spend": float(grouped["total_spend"].mean()),
        "top_customers_by_spend": grouped["total_spend"].sort_values(ascending=False).head(10).to_dict(),
    }


def rate_analysis(df: pd.DataFrame, rate_columns: list[str]) -> dict[str, Any]:
    result = {}
    for col in rate_columns:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        result[col] = {"mean": float(series.mean()), "max": float(series.max()), "min": float(series.min())}
    return result


def _find_column(role_map: dict[str, str], target_roles: tuple[str, ...], name_hints: tuple[str, ...] = ()) -> Optional[str]:
    if target_roles == ("identifier",) and any(h in name_hints for h in ("customer", "client", "buyer", "member")):
        explicit = next((c for c, r in role_map.items() if r == "customer_id"), None)
        if explicit:
            return explicit
    for col, role in role_map.items():
        if role in target_roles and (not name_hints or any(h in col for h in name_hints)):
            return col
    if name_hints and target_roles == ("identifier",):
        return None  # An order identifier must never stand in for a customer, or vice versa.
    for col, role in role_map.items():
        if role in target_roles:
            return col
    return None


def generate_kpis(df: pd.DataFrame, column_roles: dict[str, str]) -> list[dict[str, Any]]:
    """Dynamically select KPIs from detected business concepts (Section 24)."""
    kpis: list[dict[str, Any]] = []

    revenue_col = _find_column(column_roles, ("currency_amount",), ("revenue", "sales", "total", "amount"))
    quantity_col = _find_column(column_roles, ("numeric",), ("quantity", "units", "qty"))
    order_id_col = _find_column(column_roles, ("identifier",), ("order", "transaction", "invoice"))
    customer_id_col = _find_column(column_roles, ("identifier",), ("customer", "client", "buyer", "member"))
    date_col = _find_column(column_roles, ("date_time",))

    if revenue_col:
        series = pd.to_numeric(df[revenue_col], errors="coerce")
        kpis.append({"label": "Total Revenue", "value": round(float(series.sum()), 2), "source_column": revenue_col})
        kpis.append({"label": "Average Order Value", "value": round(float(series.mean()), 2), "source_column": revenue_col})

    if quantity_col:
        series = pd.to_numeric(df[quantity_col], errors="coerce")
        kpis.append({"label": "Total Units Sold", "value": round(float(series.sum()), 2), "source_column": quantity_col})

    if order_id_col:
        kpis.append({"label": "Total Orders", "value": int(df[order_id_col].nunique()), "source_column": order_id_col})

    if customer_id_col:
        kpis.append({"label": "Total Customers", "value": int(df[customer_id_col].nunique()), "source_column": customer_id_col})
        if order_id_col:
            repeat = df.groupby(customer_id_col)[order_id_col].nunique()
            kpis.append({"label": "Repeat Customers", "value": int((repeat > 1).sum()), "source_column": customer_id_col})

    if date_col and revenue_col:
        parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
        working = pd.DataFrame({date_col: parsed_dates, revenue_col: pd.to_numeric(df[revenue_col], errors="coerce")}).dropna()
        if not working.empty:
            monthly = working.set_index(date_col).resample("ME")[revenue_col].sum()
            if len(monthly) >= 2 and monthly.iloc[-2] != 0:
                growth = (monthly.iloc[-1] - monthly.iloc[-2]) / abs(monthly.iloc[-2]) * 100
                kpis.append({"label": "Month-over-Month Growth Rate (%)", "value": round(float(growth), 2), "source_column": revenue_col})

    if not kpis:
        kpis.append({"label": "Total Rows", "value": int(len(df)), "source_column": None})

    from backend.services.exploration_service import clean_json
    return clean_json(kpis)


def detected_business_columns(column_roles: dict[str, str]) -> dict[str, Optional[str]]:
    return {
        "revenue_column": _find_column(column_roles, ("currency_amount",), ("revenue", "sales", "total", "amount")),
        "quantity_column": _find_column(column_roles, ("numeric",), ("quantity", "units", "qty")),
        "order_id_column": _find_column(column_roles, ("identifier",), ("order", "transaction", "invoice")),
        "customer_id_column": _find_column(column_roles, ("identifier",), ("customer", "client", "buyer", "member")),
        "date_column": _find_column(column_roles, ("date_time",)),
        "category_column": _find_column(column_roles, ("categorical",), ("category", "product")),
        "region_column": _find_column(column_roles, ("categorical",), ("region", "state", "country", "city")),
        "payment_column": _find_column(column_roles, ("categorical",), ("payment",)),
        "discount_column": _find_column(column_roles, ("percentage_rate",), ("discount",)),
        "return_column": _find_column(column_roles, ("categorical", "percentage_rate"), ("return", "refund")),
    }
