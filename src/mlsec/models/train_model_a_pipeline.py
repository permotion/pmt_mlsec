"""
Training pipeline — Modelo A (CSIC 2010) — para DAG de Airflow

Diseñado para ser invocado como subproceso desde el DAG dag_model_a.py.

Uso:
    python train_model_a_pipeline.py [--features PARQUET_PATH] [--min-recall FLOAT]

Comportamiento:
- Lee el parquet de features (default: features_v4.parquet)
- Split estratificado 70/15/15 (mismo seed que experimentos anteriores)
- Entrena LightGBM con calibración de threshold via min_recall_val
- Loggea parámetros, métricas y threshold en MLflow (experimento mlsec-model-a)
- Exit code 0 si Recall >= min_recall en test, exit code 1 si no se cumple
  (Airflow interpreta exit 1 como tarea fallida)
"""

import argparse
import sys
import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn
from pathlib import Path
from lightgbm import LGBMClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score,
    precision_recall_curve,
    recall_score,
    precision_score,
    confusion_matrix,
)

ROOT = Path(__file__).resolve().parents[3]

RANDOM_STATE   = 42
MIN_RECALL_VAL = 0.955   # calibrado en v5 — optimizar threshold en val con este target
MIN_RECALL_TEST = 0.95   # criterio de éxito del MVP

MLFLOW_DB   = ROOT / "mlflow.db"
EXPERIMENT  = "mlsec-model-a"

CONTINUOUS_COLS = ["url_length", "url_query_length", "content_length"]


def find_best_threshold(y_true: np.ndarray, y_proba: np.ndarray, min_recall: float) -> float:
    """Threshold que maximiza Precision manteniendo Recall >= min_recall en val."""
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_proba)
    mask = recalls[:-1] >= min_recall
    if not mask.any():
        best_idx = np.argmax(recalls[:-1])
    else:
        best_idx = np.where(mask, precisions[:-1], 0).argmax()
    return float(thresholds[best_idx])


def train(features_path: Path, min_recall_val: float) -> dict:
    print(f"Cargando features desde {features_path} ...")
    df = pd.read_parquet(features_path)
    print(f"Shape: {df.shape} | Attack rate: {df['label'].mean():.1%}")

    X = df.drop(columns=["label"]).values.astype("float32")
    y = df["label"].values
    feature_names = df.drop(columns=["label"]).columns.tolist()

    # Split estratificado 70/15/15
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.30, stratify=y, random_state=RANDOM_STATE
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50, stratify=y_temp, random_state=RANDOM_STATE
    )
    print(f"Train: {len(y_train)} | Val: {len(y_val)} | Test: {len(y_test)}")

    # Escalar features continuas — fit solo en train
    continuous_idx = [feature_names.index(c) for c in CONTINUOUS_COLS if c in feature_names]
    scaler = StandardScaler()
    X_train[:, continuous_idx] = scaler.fit_transform(X_train[:, continuous_idx])
    X_val[:, continuous_idx]   = scaler.transform(X_val[:, continuous_idx])
    X_test[:, continuous_idx]  = scaler.transform(X_test[:, continuous_idx])

    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    scale_pos_weight = neg / pos

    model = LGBMClassifier(
        n_estimators=200,
        scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=-1,
    )

    print("Entrenando LightGBM ...")
    model.fit(X_train, y_train)

    # Calibrar threshold en val
    val_proba = model.predict_proba(X_val)[:, 1]
    threshold = find_best_threshold(y_val, val_proba, min_recall_val)
    print(f"Threshold calibrado (min_recall_val={min_recall_val}): {threshold:.4f}")

    # Evaluar en test
    test_proba = model.predict_proba(X_test)[:, 1]
    test_pred  = (test_proba >= threshold).astype(int)

    test_recall    = recall_score(y_test, test_pred)
    test_precision = precision_score(y_test, test_pred)
    test_roc_auc   = roc_auc_score(y_test, test_proba)
    cm = confusion_matrix(y_test, test_pred)
    fp = int(cm[0, 1])

    print(f"\n--- Resultados test ---")
    print(f"ROC-AUC:   {test_roc_auc:.4f}")
    print(f"Recall:    {test_recall:.4f}  {'✅' if test_recall >= MIN_RECALL_TEST else '❌'}")
    print(f"Precision: {test_precision:.4f}")
    print(f"FP:        {fp}")

    return dict(
        model=model,
        scaler=scaler,
        threshold=threshold,
        test_recall=test_recall,
        test_precision=test_precision,
        test_roc_auc=test_roc_auc,
        fp=fp,
        features_path=str(features_path),
        min_recall_val=min_recall_val,
        n_features=len(feature_names),
    )


def log_to_mlflow(results: dict):
    mlflow.set_tracking_uri(f"sqlite:///{MLFLOW_DB}")
    mlflow.set_experiment(EXPERIMENT)

    with mlflow.start_run(run_name="model-a-lightgbm-pipeline"):
        mlflow.log_params({
            "model":           "LightGBM",
            "features_path":   results["features_path"],
            "n_features":      results["n_features"],
            "min_recall_val":  results["min_recall_val"],
            "threshold":       round(results["threshold"], 4),
            "random_state":    RANDOM_STATE,
        })
        mlflow.log_metrics({
            "test_recall":    round(results["test_recall"], 4),
            "test_precision": round(results["test_precision"], 4),
            "test_roc_auc":   round(results["test_roc_auc"], 4),
            "test_fp":        results["fp"],
        })
        mlflow.sklearn.log_model(results["model"], artifact_path="model")
        print(f"Run loggeado en MLflow — experimento '{EXPERIMENT}'")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--features",
        type=Path,
        default=ROOT / "data" / "processed" / "csic2010" / "features_v4.parquet",
        help="Path al parquet de features",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=MIN_RECALL_VAL,
        help="Target de recall mínimo para calibración de threshold en val",
    )
    args = parser.parse_args()

    if not args.features.exists():
        print(f"ERROR: No existe {args.features} — ejecutá primero el paso de preprocessing.")
        sys.exit(1)

    results = train(args.features, args.min_recall)
    log_to_mlflow(results)

    # Exit code para Airflow
    if results["test_recall"] < MIN_RECALL_TEST:
        print(f"\nCriterio de Recall NO cumplido ({results['test_recall']:.4f} < {MIN_RECALL_TEST})")
        sys.exit(1)

    print(f"\nPipeline completado. Recall ✅ — Precision {results['test_precision']:.4f}")
    sys.exit(0)


if __name__ == "__main__":
    main()
