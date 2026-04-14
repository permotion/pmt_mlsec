"""
Preprocessing para inferencia — aplica las mismas transformaciones que el training.

El training (train_model_a_pipeline.py) usa StandardScaler en las features
continuas. El scaler se fittea SOLO en train y se aplica a val/test.
En la API necesitamos replicar esa transformación con los mismos parámetros.

Los valores del scaler se computaron del train set (70% del parquet).
"""

from __future__ import annotations

import numpy as np

CONTINUOUS_COLS = ["url_length", "url_query_length", "content_length"]

# Medidas del scaler (fit en train durante el último run del DAG)
SCALER_MEAN = np.array([90.3179, 33.9456, 31.9591], dtype="float32")
SCALER_STD = np.array([75.4913, 77.8077, 76.0520], dtype="float32")


def scale_continuous(features: np.ndarray, feature_names: list[str]) -> np.ndarray:
    """
    Aplica StandardScaler a las features continuas.

    Args:
        features: array de shape (1, n_features) con valores crudos
        feature_names: lista de nombres de features en orden

    Returns:
        array con las features continuas escaladas
    """
    features = features.copy()
    for i, col in enumerate(CONTINUOUS_COLS):
        idx = feature_names.index(col)
        features[0, idx] = (features[0, idx] - SCALER_MEAN[i]) / SCALER_STD[i]
    return features
