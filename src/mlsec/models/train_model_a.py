"""
Training baseline — Modelo A (CSIC 2010)

Dataset: data/processed/csic2010/features.parquet
Objetivo: Recall >= 0.95 / Precision >= 0.85

Estrategia:
- Split estratificado 70/15/15 (train/val/test)
- Baseline: Logistic Regression con class_weight='balanced'
- Threshold optimizado por curva ROC (no se asume 0.5)
- Métricas reportadas: Recall, Precision, F1, ROC-AUC
"""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    precision_recall_curve,
    recall_score,
    precision_score,
)

ROOT     = Path(__file__).resolve().parents[3]
DATA_PATH = ROOT / "data" / "processed" / "csic2010" / "features.parquet"

# Criterios de éxito (docs/models.md)
MIN_RECALL    = 0.95
MIN_PRECISION = 0.85

RANDOM_STATE = 42


def find_best_threshold(y_true: np.ndarray, y_proba: np.ndarray) -> float:
    """
    Encuentra el threshold que maximiza Recall >= MIN_RECALL
    con la mayor Precision posible.
    """
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_proba)
    # Filtrar thresholds donde Recall >= mínimo exigido
    mask = recalls[:-1] >= MIN_RECALL
    if not mask.any():
        # Si ningún threshold cumple, tomar el de mayor Recall
        best_idx = np.argmax(recalls[:-1])
    else:
        # De los que cumplen Recall, tomar el de mayor Precision
        best_idx = np.where(mask, precisions[:-1], 0).argmax()
    return float(thresholds[best_idx])


def evaluate(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray, split_name: str):
    print(f"\n{'='*50}")
    print(f"Resultados — {split_name}")
    print(f"{'='*50}")
    print(classification_report(y_true, y_pred, target_names=["Normal", "Attack"], digits=4))
    print(f"ROC-AUC: {roc_auc_score(y_true, y_proba):.4f}")
    print(f"\nConfusion matrix:")
    cm = confusion_matrix(y_true, y_pred)
    print(f"  TN={cm[0,0]}  FP={cm[0,1]}")
    print(f"  FN={cm[1,0]}  TP={cm[1,1]}")


def train():
    print("Cargando datos...")
    df = pd.read_parquet(DATA_PATH)

    X = df.drop(columns=["label"]).values.astype("float32")
    y = df["label"].values

    # Split estratificado 70 / 15 / 15
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.30, stratify=y, random_state=RANDOM_STATE
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50, stratify=y_temp, random_state=RANDOM_STATE
    )

    print(f"Train: {len(y_train)} | Val: {len(y_val)} | Test: {len(y_test)}")
    print(f"Train attack rate: {y_train.mean():.1%}")

    # Escalar features continuas (url_length, content_length) — fit solo en train
    # Índices de las columnas continuas en el feature set
    feature_names = df.drop(columns=["label"]).columns.tolist()
    continuous_idx = [feature_names.index(c) for c in ["url_length", "content_length"]]

    scaler = StandardScaler()
    X_train[:, continuous_idx] = scaler.fit_transform(X_train[:, continuous_idx])
    X_val[:, continuous_idx]   = scaler.transform(X_val[:, continuous_idx])
    X_test[:, continuous_idx]  = scaler.transform(X_test[:, continuous_idx])

    def run_model(name, model, X_tr, X_v, X_te):
        print(f"\n{'='*50}")
        print(f"Modelo: {name}")
        print(f"{'='*50}")
        model.fit(X_tr, y_train)

        val_proba  = model.predict_proba(X_v)[:, 1]
        threshold  = find_best_threshold(y_val, val_proba)
        print(f"Threshold óptimo (val): {threshold:.4f}")

        val_pred = (val_proba >= threshold).astype(int)
        evaluate(y_val, val_pred, val_proba, f"Validation (threshold={threshold:.4f})")

        test_proba = model.predict_proba(X_te)[:, 1]
        test_pred  = (test_proba >= threshold).astype(int)
        evaluate(y_test, test_pred, test_proba, f"Test (threshold={threshold:.4f})")

        rc = recall_score(y_test, test_pred)
        pr = precision_score(y_test, test_pred)
        print(f"\nCriterios de éxito:")
        print(f"  Recall:    {rc:.4f}  (mínimo {MIN_RECALL})  {'✅' if rc >= MIN_RECALL else '❌'}")
        print(f"  Precision: {pr:.4f}  (mínimo {MIN_PRECISION})  {'✅' if pr >= MIN_PRECISION else '❌'}")
        return model, threshold

    # Ratio para scale_pos_weight en XGBoost/LightGBM
    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    scale = neg / pos

    # --- Logistic Regression (baseline) ---
    lr = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    run_model("Logistic Regression", lr, X_train, X_val, X_test)

    # --- Random Forest ---
    rf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    run_model("Random Forest", rf, X_train, X_val, X_test)

    # --- XGBoost ---
    xgb = XGBClassifier(
        n_estimators=200,
        scale_pos_weight=scale,
        eval_metric="logloss",
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbosity=0,
    )
    run_model("XGBoost", xgb, X_train, X_val, X_test)

    # --- LightGBM ---
    lgbm = LGBMClassifier(
        n_estimators=200,
        scale_pos_weight=scale,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=-1,
    )
    model, threshold = run_model("LightGBM", lgbm, X_train, X_val, X_test)

    return model, threshold


if __name__ == "__main__":
    train()
