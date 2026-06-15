#!/usr/bin/env python3
"""
Promueve un modelo de Staging a Production en el MLflow Model Registry.

Uso:
    python scripts/promote_model_to_production.py [--version V] [--experiment NAME]

Flujo:
    1. Lista los modelos en Staging con sus métricas
    2. Si se especifica --version, promociona esa versión
    3. Si no, promociona la última versión en Staging
    4. El modelo que estaba en Production pasa a Archived

Ejemplo:
    # Ver modelos en Staging
    python scripts/promote_model_to_production.py --list

    # Promover la última versión de Staging a Production
    python scripts/promote_model_to_production.py

    # Promover una versión específica
    python scripts/promote_model_to_production.py --version 5
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

# Agregar src al path para poder importar desde ahí
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import mlflow
from mlflow.tracking import MlflowClient


MLFLOW_DB = ROOT / "mlflow.db"
EXPERIMENT = "mlsec-model-a"


def get_tracking_uri(tracking_uri=None):
    """Resolve MLflow tracking URI."""
    if tracking_uri:
        return tracking_uri
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        return uri
    return f"sqlite:///{MLFLOW_DB}"


def fmt_metric(value, fmt=".4f"):
    """Format a metric value or return N/A."""
    if value is None or value == "N/A":
        return "N/A"
    try:
        return format(float(value), fmt)
    except (TypeError, ValueError):
        return str(value)


def list_staging_models(tracking_uri: str):
    """Lista todos los modelos en alias Staging con sus métricas."""
    import warnings
    warnings.filterwarnings("ignore", message=".*get_latest_versions.*deprecated.*")
    warnings.filterwarnings("ignore", message=".*Model registry stages.*")
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()

    try:
        version = client.get_model_version_by_alias(EXPERIMENT, "staging")
    except mlflow.exceptions.MlflowException:
        print(f"\nNo hay modelos con alias 'staging' para '{EXPERIMENT}'.")
        print("Primero hay que entrenar un modelo que pase los criterios de candidate.")
        return []

    print(f"\nModelos en Staging — experimento '{EXPERIMENT}':\n")
    header = f"{'Ver':>4}  {'Alias':<10}  {'Run ID':<8}  {'Recall':>7}  {'Precision':>9}  {'Gap':>7}  {'Threshold':>9}  {'Tag':<12}  Entrenado"
    print(header)
    print("-" * len(header))

    rows = []
    run = client.get_run(version.run_id)
    metrics = run.data.metrics
    params = run.data.params
    tags = {t.key: t.value for t in client.get_model_version_tags(EXPERIMENT, version.version)}

    trained_at = tags.get("trained_at", "N/A")
    if trained_at != "N/A" and trained_at:
        try:
            trained_at = trained_at[:10]
        except Exception:
            pass

    row = (
        f"{version.version:>4}  "
        f"staging       "
        f"{version.run_id[:8]:<8}  "
        f"{fmt_metric(metrics.get('test_recall')):>7}  "
        f"{fmt_metric(metrics.get('test_precision')):>9}  "
        f"{fmt_metric(metrics.get('gap_recall')):>7}  "
        f"{fmt_metric(params.get('threshold')):>9}  "
        f"{tags.get('deployment_stage', 'N/A'):<12}  "
        f"{trained_at}"
    )
    print(row)
    rows.append(version)


def list_production_models(tracking_uri: str):
    """Lista el modelo actual en Production."""
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()

    try:
        versions = client.get_latest_versions(EXPERIMENT, stages=["Production"])
    except mlflow.exceptions.MlflowException as e:
        if "Registered Model" in str(e) and "not found" in str(e):
            return None
        raise

    if not versions:
        print("No hay modelo en Production.")
        return None

    v = versions[0]
    run = client.get_run(v.run_id)
    metrics = run.data.metrics
    params = run.data.params

    print(f"\nModelo actual en Production:")
    print(f"  Versión:   v{v.version}")
    print(f"  Run ID:    {v.run_id}")
    print(f"  Recall:    {fmt_metric(metrics.get('test_recall'))}")
    print(f"  Precision: {fmt_metric(metrics.get('test_precision'))}")
    print(f"  Threshold: {fmt_metric(params.get('threshold'))}")
    return v


def promote_model(version: int | None, tracking_uri: str):
    """Promueve un modelo de Staging a Production."""
    import warnings
    warnings.filterwarnings("ignore", message=".*get_latest_versions.*deprecated.*")
    warnings.filterwarnings("ignore", message=".*Model registry stages.*")
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()

    # Obtener versión a promover — buscar por alias staging
    try:
        staging_version = client.get_model_version_by_alias(EXPERIMENT, "staging")
    except mlflow.exceptions.MlflowException:
        print(f"No hay modelos con alias 'staging' para '{EXPERIMENT}'.")
        print("Primero hay que entrenar un modelo que pase los criterios de candidate.")
        sys.exit(1)

    target_version = int(staging_version.version)

    # Obtener run y métricas
    run = client.get_run(staging_version.run_id)

    print(f"\nPromoviendo modelo v{target_version} a Production:")
    print(f"  Run ID:     {run.info.run_id}")
    print(f"  Recall:     {fmt_metric(run.data.metrics.get('test_recall'))}")
    print(f"  Precision:  {fmt_metric(run.data.metrics.get('test_precision'))}")
    print(f"  ROC-AUC:    {fmt_metric(run.data.metrics.get('test_roc_auc'))}")
    print(f"  Gap recall: {fmt_metric(run.data.metrics.get('gap_recall'))}")
    print(f"  Threshold:  {fmt_metric(run.data.params.get('threshold'))}")

    # Archivar el Production actual si existe
    try:
        old_prod = client.get_model_version_by_alias(EXPERIMENT, "production")
        client.set_registered_model_alias(EXPERIMENT, "archived", old_prod.version)
        print(f"\n  Production anterior (v{old_prod.version}) → Archived")
    except mlflow.exceptions.MlflowException:
        pass  # No hay Production anterior

    # Promover a Production
    client.set_registered_model_alias(EXPERIMENT, "production", target_version)

    # Tags de metadata
    client.set_model_version_tag(
        EXPERIMENT, target_version, "deployment_stage", "production"
    )
    client.set_model_version_tag(
        EXPERIMENT, target_version, "promoted_at", datetime.now().isoformat()
    )

    print(f"\n  v{target_version} → Production")
    print(f"\nLa API puede cargar este modelo con get_model(stage='Production')")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promover modelo a Production")
    parser.add_argument(
        "--list", dest="list_only", action="store_true",
        help="Solo listar modelos en Staging (no promover)"
    )
    parser.add_argument(
        "--version", type=int, default=None,
        help="Versión específica a promover (default: última)"
    )
    parser.add_argument(
        "--experiment", default=EXPERIMENT,
        help=f"Nombre del experimento (default: {EXPERIMENT})"
    )
    parser.add_argument(
        "--tracking-uri",
        help="MLflow tracking URI (default: sqlite:///mlflow.db o MLFLOW_TRACKING_URI)"
    )

    args = parser.parse_args()
    EXPERIMENT = args.experiment
    tracking_uri = get_tracking_uri(args.tracking_uri)

    if args.list_only:
        list_staging_models(tracking_uri)
        list_production_models(tracking_uri)
    else:
        promote_model(args.version, tracking_uri)
