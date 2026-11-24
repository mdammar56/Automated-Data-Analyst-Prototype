"""
backend/ml/anomaly_detection.py

Isolation Forest and Local Outlier Factor implementations used by
backend/cleaning/anomalies.py (Section 16.5). Both operate purely on the
numeric feature matrix and never assume a fixed schema.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler


def _prepare_matrix(df: pd.DataFrame, columns: list[str]) -> np.ndarray:
    matrix = df[columns].apply(pd.to_numeric, errors="coerce")
    imputer = SimpleImputer(strategy="median")
    imputed = imputer.fit_transform(matrix)
    scaler = StandardScaler()
    return scaler.fit_transform(imputed)


def run_isolation_forest(
    df: pd.DataFrame, columns: list[str], contamination: float = "auto", random_state: int = 42
) -> dict[str, Any]:
    X = _prepare_matrix(df, columns)
    model = IsolationForest(
        n_estimators=200,
        contamination=0.02 if contamination == "auto" else contamination,
        random_state=random_state,
    )
    predictions = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    scores = model.score_samples(X)  # higher = more normal
    flags = pd.Series(predictions == -1, index=df.index)
    return {"flags": flags, "scores": pd.Series(scores, index=df.index)}


def run_local_outlier_factor(
    df: pd.DataFrame, columns: list[str], n_neighbors: int = 20
) -> dict[str, Any]:
    X = _prepare_matrix(df, columns)
    n_neighbors = min(n_neighbors, max(2, len(X) - 1))
    model = LocalOutlierFactor(n_neighbors=n_neighbors, novelty=False)
    predictions = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    flags = pd.Series(predictions == -1, index=df.index)
    return {"flags": flags, "scores": pd.Series(model.negative_outlier_factor_, index=df.index)}
