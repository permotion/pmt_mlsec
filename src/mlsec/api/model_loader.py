"""
Carga el modelo LightGBM para inferencia.

Preferencias de carga (en orden):
1. Desde un archivo pickle local (MODEL_PATH)
2. Desde MLflow (MLFLOW_TRACKING_URI + run_id)

Si ninguno está disponible, levanta una excepción.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import mlflow
from mlflow.tracking import MlflowClient

ROOT = Path(__file__).resolve().parents[3]

# Threshold calibrado en el último entrenamiento (DAG run 2026-04-13)
# Este valor debería actualizarse cuando se reentrene con nuevas features.
THRESHOLD = 0.2903

# Versión del modelo — se muestra en las respuestas
MODEL_VERSION = "v1-dag-2026-04-13"

# ---------------------------------------------------------------------------
# Carga desde pickle local
# ---------------------------------------------------------------------------
MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    str(ROOT / "models" / "model_a_lightgbm.pkl"),
)


def load_model_from_pickle() -> tuple:
    """
    Carga (model, scaler, threshold) desde un pickle local.
    Raise FileNotFoundError si no existe.
    """
    import pickle

    if not Path(MODEL_PATH).exists():
        raise FileNotFoundError(f"Modelo no encontrado en: {MODEL_PATH}")

    with open(MODEL_PATH, "rb") as f:
        model, scaler, threshold = pickle.load(f)

    return model, scaler, threshold


# ---------------------------------------------------------------------------
# Carga desde MLflow
# ---------------------------------------------------------------------------
def load_model_from_mlflow(
    run_id: str | None = None,
    experiment_name: str = "mlsec-model-a",
    tracking_uri: str | None = None,
) -> tuple:
    """
    Descarga el artefacto del último run exitoso del experimento desde MLflow.

    Args:
        run_id: ID específico del run. Si es None, usa el último del experimento.
        experiment_name: Nombre del experimento en MLflow.
        tracking_uri: URI del servidor MLflow. Si es None, usa MLFLOW_TRACKING_URI o SQLite local.

    Returns:
        (model, scaler, threshold)
    """
    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        mlflow.set_tracking_uri(uri)

    client = MlflowClient()

    # Encontrar el run
    if run_id is None:
        exp = client.get_experiment_by_name(experiment_name)
        if exp is None:
            raise RuntimeError(f"Experimento '{experiment_name}' no encontrado en MLflow")
        runs = client.search_runs(
            experiment_ids=[exp.experiment_id],
            filter_string="attributes.status = 'FINISHED'",
            order_by=["metrics.test_recall DESC"],
        )
        if not runs:
            raise RuntimeError(f"No se encontraron runs terminados en '{experiment_name}'")
        run = runs[0]
        run_id = run.info.run_id
    else:
        run = client.get_run(run_id)

    # Descargar el artefacto a un directorio temporal
    artifact_uri = client.get_run(run_id).info.artifact_uri

    # MLflow devuelve file:///opt/mlflow/artifacts/... (ruta interna del contenedor).
    # Esto solo es accesible desde dentro del contenedor mlflow.
    # Lo convertimos a la URL del proxy nginx (disponible desde cualquier contenedor
    # en la misma red Docker, y expuesto al host en puerto 5083).
    ARTIFACT_PROXY = os.environ.get(
        "MLFLOW_ARTIFACT_PROXY", "http://nginx-artifacts:80"
    )
    if "opt/mlflow/artifacts" in artifact_uri:
        # Quitar el prefijo /opt/mlflow/artifacts/ (con o sin file://)
        artifact_path = artifact_uri.replace("file:///opt/mlflow/artifacts/", "").replace("/opt/mlflow/artifacts/", "")
        artifact_uri = f"{ARTIFACT_PROXY}/{artifact_path}"
        print(f"Artefacto convertido a HTTP: {artifact_uri}")

    local_path = mlflow.artifacts.download_artifacts(
        artifact_uri=artifact_uri,
        dst_path="/tmp/mlflow_model",
    )

    import pickle

    model_path = Path(local_path) / "model.pkl"
    if not model_path.exists():
        # MLflow 2.x serializa como sklearn en model.pkl
        raise FileNotFoundError(
            f"Artefacto 'model.pkl' no encontrado en {local_path}. "
            "Verificá que el run fue loggeado con log_model()."
        )

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    # Threshold — se loggea como parámetro
    threshold = float(run.data.params.get("threshold", THRESHOLD))
    scaler = None  # El scaler no se persiste en MLflow por default

    return model, scaler, threshold


# ---------------------------------------------------------------------------
# Interfaz unificada
# ---------------------------------------------------------------------------
def get_model():
    """
    Carga el modelo. Intenta pickle local primero, luego MLflow.
    """
    if Path(MODEL_PATH).exists():
        print(f"Cargando modelo desde pickle: {MODEL_PATH}")
        return load_model_from_pickle()

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        print(f"Cargando modelo desde MLflow: {tracking_uri}")
        return load_model_from_mlflow(tracking_uri=tracking_uri)

    raise RuntimeError(
        "No se encontró modelo local y MLFLOW_TRACKING_URI no está seteado. "
        f"Configurá MODEL_PATH o MLFLOW_TRACKING_URI."
    )
