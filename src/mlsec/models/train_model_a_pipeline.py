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
import os
import sys
import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn
from pathlib import Path
from lightgbm import LGBMClassifier
from sklearn.model_selection import train_test_split
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

    # Evaluar en train con el mismo threshold (detectar overfitting)
    train_proba = model.predict_proba(X_train)[:, 1]
    train_pred  = (train_proba >= threshold).astype(int)
    train_recall = recall_score(y_train, train_pred)
    print(f"Train Recall (threshold={threshold:.4f}): {train_recall:.4f}")

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
        threshold=threshold,
        train_recall=train_recall,
        test_recall=test_recall,
        test_precision=test_precision,
        test_roc_auc=test_roc_auc,
        gap_recall=train_recall - test_recall,
        fp=fp,
        features_path=str(features_path),
        min_recall_val=min_recall_val,
        n_features=len(feature_names),
    )


def log_to_mlflow(results: dict):
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{MLFLOW_DB}")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT)

    with mlflow.start_run(run_name="model-a-lightgbm-pipeline") as run:
        mlflow.log_params({
            "model":           "LightGBM",
            "features_path":   results["features_path"],
            "n_features":      results["n_features"],
            "min_recall_val":  results["min_recall_val"],
            "threshold":       round(results["threshold"], 4),
            "random_state":    RANDOM_STATE,
        })
        mlflow.log_metrics({
            "train_recall":   round(results["train_recall"], 4),
            "test_recall":    round(results["test_recall"], 4),
            "gap_recall":     round(results["train_recall"] - results["test_recall"], 4),
            "test_precision": round(results["test_precision"], 4),
            "test_roc_auc":   round(results["test_roc_auc"], 4),
            "test_fp":        results["fp"],
        })
        mlflow.sklearn.log_model(results["model"], name="model")
        print(f"Run loggeado en MLflow — experimento '{EXPERIMENT}'")
        return run.info.run_id


def register_to_registry(run_id: str, results: dict):
    """
    Registra el modelo en MLflow Model Registry si pasa los criterios de candidate.

    Criterios:
        - test_recall >= 0.95
        - test_precision >= 0.75
        - gap_recall <= 0.05

    Si pasa → stage=Staging (candidato para blue team)
    Si no pasa → solo se loggea en MLflow, sin registro
    """
    criteria = {
        "test_recall":    0.95,
        "test_precision": 0.75,
        "gap_recall":     0.05,
    }

    passed = (
        results["test_recall"] >= criteria["test_recall"]
        and results["test_precision"] >= criteria["test_precision"]
        and results["gap_recall"] <= criteria["gap_recall"]
    )

    if not passed:
        print("Modelo no pasa criterios de candidate — no se registra en Registry")
        return None

    from mlflow.tracking import MlflowClient

    client = MlflowClient()

    # MLflow 3.x: usar MlflowClient.register_model() con run_id separado
    model_uri = f"runs://{run_id}/model"
    registered = client.register_model(model_uri, EXPERIMENT, run_id=run_id)
    client.transition_model_version_stage(EXPERIMENT, registered.version, stage="Staging")

    # Tags de metadata
    client.set_model_version_tag(
        EXPERIMENT, registered.version, "deployment_stage", "candidate"
    )
    client.set_model_version_tag(
        EXPERIMENT, registered.version, "trained_at", pd.Timestamp.now().isoformat()
    )

    print(
        f"Modelo registrado en MLflow Registry: {EXPERIMENT} v{registered.version} "
        f"(stage=Staging, deployment_stage=candidate)"
    )
    return registered


def register_last_run() -> bool:
    """
    Lee el último run del experimento mlsec-model-a desde MLflow
    y lo registra en el Model Registry si pasa los criterios.

    Returns:
        True si se registró, False si no.
    """
    from mlflow.tracking import MlflowClient

    criteria = {
        "test_recall":    0.95,
        "test_precision": 0.75,
        "gap_recall":     0.05,
    }

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{MLFLOW_DB}")
    mlflow.set_tracking_uri(tracking_uri)

    client = MlflowClient()
    exp = client.get_experiment_by_name(EXPERIMENT)
    if exp is None:
        print(f"Experimento '{EXPERIMENT}' no encontrado en MLflow")
        return False

    # Buscar el último run terminado, ordenado por start_time DESC
    runs = client.search_runs(
        experiment_ids=[exp.experiment_id],
        filter_string="attributes.status = 'FINISHED'",
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )

    if not runs:
        print("No se encontraron runs terminados")
        return False

    run = runs[0]
    run_id = run.info.run_id
    exp_id = run.info.experiment_id
    metrics = run.data.metrics

    print(f"\nÚltimo run: {run_id}")
    print(f"  test_recall:    {metrics.get('test_recall', 'N/A')}")
    print(f"  test_precision: {metrics.get('test_precision', 'N/A')}")
    print(f"  gap_recall:     {metrics.get('gap_recall', 'N/A')}")

    # Verificar criterios
    test_recall = metrics.get("test_recall")
    test_precision = metrics.get("test_precision")
    gap_recall = metrics.get("gap_recall")

    if test_recall is None or test_precision is None or gap_recall is None:
        print("Run sin métricas completas — no se registra")
        return False

    passed = (
        test_recall >= criteria["test_recall"]
        and test_precision >= criteria["test_precision"]
        and gap_recall <= criteria["gap_recall"]
    )

    if not passed:
        print(
            f"Modelo no pasa criterios de candidate "
            f"(recall≥{criteria['test_recall']}, precision≥{criteria['test_precision']}, "
            f"gap≤{criteria['gap_recall']}) — no se registra en Registry"
        )
        return False

    # MLflow 3.x — buscar logged models del run
    logged_models = client.search_logged_models(
        experiment_ids=[exp.experiment_id],
        filter_string=f"source_run_id = '{run_id}'",
        max_results=1,
    )

    if not logged_models:
        print(f"No se encontró ningún logged model para run {run_id}")
        return False

    model_id = logged_models[0].model_id
    model_uri = f"models:/{model_id}"

    # Registrar con la URI correcta
    registered = mlflow.register_model(model_uri, EXPERIMENT)

    # Setear alias staging
    client.set_registered_model_alias(EXPERIMENT, "staging", registered.version)

    client.set_model_version_tag(
        EXPERIMENT, registered.version, "deployment_stage", "candidate"
    )
    client.set_model_version_tag(
        EXPERIMENT, registered.version, "trained_at", pd.Timestamp.now().isoformat()
    )

    print(
        f"\n✅ Modelo registrado: {EXPERIMENT} v{registered.version} "
        f"(alias=staging, deployment_stage=candidate)"
    )
    return True


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
    parser.add_argument(
        "--register-only",
        action="store_true",
        help="Solo registra el último run en MLflow Registry (sin entrenar)",
    )
    args = parser.parse_args()

    if args.register_only:
        # Solo registra el último run — para la task "register" del DAG
        success = register_last_run()
        sys.exit(0 if success else 1)

    if not args.features.exists():
        print(f"ERROR: No existe {args.features} — ejecutá primero el paso de preprocessing.")
        sys.exit(1)

    results = train(args.features, args.min_recall)
    run_id = log_to_mlflow(results)

    # Exit code para Airflow
    if results["test_recall"] < MIN_RECALL_TEST:
        print(f"\nCriterio de Recall NO cumplido ({results['test_recall']:.4f} < {MIN_RECALL_TEST})")
        sys.exit(1)

    print(f"\nPipeline completado. Recall ✅ — Precision {results['test_precision']:.4f}")
    sys.exit(0)


if __name__ == "__main__":
    main()
