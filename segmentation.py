"""
backend/ml/segmentation.py

Customer Segmentation Module (Section 28). Offers RFM analysis when
transaction/date/customer fields are present, plus K-Means (and optional
DBSCAN) clustering over suitable numeric customer features. The module never
assumes the same features exist in every dataset — it inspects the detected
column roles first and degrades gracefully when data is insufficient.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler


def rfm_eligible(customer_col: Optional[str], date_col: Optional[str], amount_col: Optional[str]) -> bool:
    return all([customer_col, date_col, amount_col])


def compute_rfm(
    df: pd.DataFrame, customer_col: str, date_col: str, amount_col: str
) -> pd.DataFrame:
    if len({customer_col, date_col, amount_col}) != 3:
        return pd.DataFrame()
    if pd.api.types.is_numeric_dtype(df[date_col]):
        return pd.DataFrame()  # Numeric measures are not transaction timestamps.
    working = df[[customer_col, date_col, amount_col]].dropna(subset=[customer_col]).copy()
    working[date_col] = pd.to_datetime(working[date_col], errors="coerce", utc=True, format="mixed")
    working[amount_col] = pd.to_numeric(working[amount_col], errors="coerce")
    working[amount_col] = working[amount_col].replace([np.inf, -np.inf], np.nan)
    working = working.dropna(subset=[date_col, amount_col])
    working = working[~working[customer_col].astype(str).str.strip().str.lower().isin(["", "unknown", "nan", "none"])]

    snapshot_date = working[date_col].max() + pd.Timedelta(days=1)
    rfm = working.groupby(customer_col).agg(
        recency_days=(date_col, lambda s: (snapshot_date - s.max()).days),
        frequency=(date_col, "count"),
        monetary=(amount_col, "sum"),
    ).reset_index()
    return rfm


def score_rfm(rfm: pd.DataFrame) -> pd.DataFrame:
    """Assign 1-4 quartile scores per RFM dimension and a combined segment label."""
    scored = rfm.copy()
    scored["r_score"] = pd.qcut(scored["recency_days"].rank(method="first"), 4, labels=[4, 3, 2, 1]).astype(int)
    scored["f_score"] = pd.qcut(scored["frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    scored["m_score"] = pd.qcut(scored["monetary"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    scored["rfm_score"] = scored["r_score"] + scored["f_score"] + scored["m_score"]

    def label(row) -> str:
        if row["rfm_score"] >= 10:
            return "Champions"
        if row["rfm_score"] >= 8:
            return "Loyal Customers"
        if row["rfm_score"] >= 6:
            return "Potential Loyalists"
        if row["rfm_score"] >= 4:
            return "At Risk"
        return "Lost / Inactive"

    scored["segment"] = scored.apply(label, axis=1)
    return scored


def kmeans_segments(df: pd.DataFrame, feature_columns: list[str], n_clusters: int = 4) -> dict[str, Any]:
    if not isinstance(n_clusters, int) or not 2 <= n_clusters <= 20:
        return {"eligible": False, "reason": "Choose between 2 and 20 clusters."}
    usable = [c for c in feature_columns if c in df.columns and not c.startswith("_") and c != "id" and not c.endswith(("_id", "_code"))]
    matrix = df[usable].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    usable = [c for c in usable if matrix[c].nunique() > 1]
    if not usable:
        return {"eligible": False, "reason": "No varying numeric features after excluding identifiers. Try EDA or categorical summaries."}
    matrix = matrix[usable].dropna(how="all")
    matrix = matrix.fillna(matrix.median())
    if len(matrix) < n_clusters * 2:
        return {"eligible": False, "reason": "Not enough numeric rows for clustering."}
    if len(matrix.drop_duplicates()) < n_clusters:
        return {"eligible": False, "reason": "Not enough distinct feature combinations for the requested cluster count."}

    scaler = StandardScaler()
    X = scaler.fit_transform(matrix)
    model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = model.fit_predict(X)

    result = matrix.copy()
    result["cluster"] = labels

    profile = result.groupby("cluster")[usable].mean().round(2)
    segment_names = _name_clusters(profile)

    return {
        "eligible": True,
        "features_used": usable,
        "cluster_sizes": result["cluster"].value_counts().to_dict(),
        "cluster_profile": profile.to_dict(orient="index"),
        "segment_names": segment_names,
        "scatter": {"x": usable[0], "y": usable[1], "points": result[[usable[0], usable[1], "cluster"]].head(1000).to_dict(orient="records")} if len(usable) >= 2 else None,
        "visualization_note": "Scatter shows up to 1,000 rows using median-imputed feature values; clustering uses all eligible rows." if len(usable) >= 2 else "A scatter plot needs two varying numeric features. Cluster distribution and means are shown instead.",
        "rows_used": len(matrix),
        "rows_excluded": len(df) - len(matrix),
    }


def dbscan_segments(df: pd.DataFrame, feature_columns: list[str], eps: float = 0.8, min_samples: int = 5) -> dict[str, Any]:
    usable = [c for c in feature_columns if c in df.columns]
    matrix = df[usable].apply(pd.to_numeric, errors="coerce").dropna()
    if len(matrix) < min_samples * 2:
        return {"eligible": False, "reason": "Not enough numeric rows for DBSCAN."}

    scaler = StandardScaler()
    X = scaler.fit_transform(matrix)
    model = DBSCAN(eps=eps, min_samples=min_samples)
    labels = model.fit_predict(X)
    result = matrix.copy()
    result["cluster"] = labels
    return {
        "eligible": True,
        "features_used": usable,
        "cluster_sizes": result["cluster"].value_counts().to_dict(),
        "noise_points": int((labels == -1).sum()),
    }


def _name_clusters(profile: pd.DataFrame) -> dict[int, str]:
    """Generate human-readable segment names only after interpreting the
    actual cluster characteristics, rather than assigning arbitrary labels."""
    names: dict[int, str] = {}
    if profile.empty:
        return names
    overall_mean = profile.mean()
    for cluster_id, row in profile.iterrows():
        relative = (row - overall_mean) / overall_mean.replace(0, np.nan).abs()
        top_dim = relative.abs().idxmax() if not relative.isna().all() else None
        if top_dim is None:
            names[int(cluster_id)] = f"Segment {cluster_id}"
            continue
        direction = "High" if relative[top_dim] > 0 else "Low"
        names[int(cluster_id)] = f"{direction} {top_dim.replace('_', ' ').title()} Segment"
    return names
