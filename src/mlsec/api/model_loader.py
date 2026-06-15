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

# Threshold calibrado en val con features_v4.parquet (sin scaler — G1/G2)
# Latest run: 2026-04-20 — threshold 0.3002
# Para threshold de producción (99:1): 0.4723 — documentado en roadmap y glossary
THRESHOLD = 0.3002

# Versión del modelo — se muestra en las respuestas
MODEL_VERSION = "v4-dag-2026-04-21"  # Pending: update after next re-training

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
    import mlflow as _mlflow_local
    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        _mlflow_local.set_tracking_uri(uri)

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

    local_path = _mlflow_local.artifacts.download_artifacts(
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
        try:
            model, scaler, threshold = pickle.load(f)
        except ValueError:
            # MLflow sklearn.log_model solo guarda el modelo (sin tuple)
            model = pickle.load(f)
            scaler = None

    # Threshold — se loggea como parámetro
    threshold = float(run.data.params.get("threshold", THRESHOLD))
    scaler = None  # El scaler no se persiste en MLflow por default

    return model, scaler, threshold


# ---------------------------------------------------------------------------
# Carga desde MLflow Model Registry (por stage)
# ---------------------------------------------------------------------------
def load_model_from_registry(
    stage: str = "Production",
    experiment_name: str = "mlsec-model-a",
    tracking_uri: str | None = None,
) -> tuple:
    """
    Carga el modelo desde MLflow Model Registry usando alias (MLflow 3.x).

    Args:
        stage: Alias del modelo — "Production" (default), "Staging", o "Archived"
        experiment_name: Nombre del registered model en MLflow
        tracking_uri: URI del servidor MLflow

    Returns:
        (model, scaler, threshold)
    """
    # Normalizar a minúsculas (MLflow aliases son case-sensitive)
    stage = stage.lower()

    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        import mlflow as _mlf
        _mlf.set_tracking_uri(uri)

    client = MlflowClient()

    # MLflow 3.x: usar get_model_version_by_alias en vez de get_latest_versions(stages=[...])
    try:
        version = client.get_model_version_by_alias(experiment_name, stage)
    except Exception as e:
        raise RuntimeError(f"No hay modelo con alias '{stage}' en el registry '{experiment_name}': {e}") from e

    print(f"Cargando modelo desde MLflow Registry: {experiment_name} v{version.version} (alias={stage})")

    # Obtener threshold del run
    run = client.get_run(version.run_id)
    threshold = float(run.data.params.get("threshold", THRESHOLD))

    # Descargar artefacto — MLflow 3.x usa models:/ URI, no file://
    # mlflow.artifacts.download_artifacts() maneja ambos esquemas directamente
    import mlflow as _mlf
    local_path = _mlf.artifacts.download_artifacts(
        artifact_uri=version.source,  # source es models:/m-xxx para MLflow 3.x
        dst_path="/tmp/mlflow_model",
    )

    import pickle

    model_path = Path(local_path)
    # MLflow 3.x log_model guarda en directorio con MLmodel, no model.pkl
    # Buscar el archivo de modelo real
    if model_path.is_dir():
        # Es un directorio — buscar MLmodel o el.pkl
        if (model_path / "MLmodel").exists():
            # MLflow 3.x format — cargar con mlflow.sklearn.load_model
            import mlflow.sklearn as _mlflow_sklearn
            model = _mlflow_sklearn.load_model(str(model_path))
            scaler = None
            return model, scaler, threshold
        # Buscar cualquier .pkl en el directorio
        pkl_files = list(model_path.glob("*.pkl"))
        if pkl_files:
            model_path = pkl_files[0]
        else:
            raise FileNotFoundError(f"No se encontró modelo en {local_path}")

    with open(model_path, "rb") as f:
        try:
            model, scaler, threshold = pickle.load(f)
        except ValueError:
            # MLflow sklearn.log_model solo guarda el modelo (sin tuple)
            model = pickle.load(f)
            scaler = None

    scaler = None
    return model, scaler, threshold


# ---------------------------------------------------------------------------
# Interfaz unificada
# ---------------------------------------------------------------------------
def get_model(stage: str = "Production"):
    """
    Carga el modelo. Por alias desde MLflow Registry (Production por default).

    Fallback: si no hay registro en Registry, usa el archivo pickle local.
    """
    # Normalizar a minúsculas (MLflow aliases son case-sensitive)
    stage = stage.lower()

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        try:
            return load_model_from_registry(stage=stage, tracking_uri=tracking_uri)
        except RuntimeError as e:
            print(f"Registry no disponible: {e}")
        except Exception as e:
            import traceback
            print(f"Error conectando a MLflow Registry: {type(e).__name__}: {e}")
            traceback.print_exc()

    # Fallback a pickle local
    if Path(MODEL_PATH).exists():
        print(f"Cargando modelo desde pickle: {MODEL_PATH}")
        return load_model_from_pickle()

    raise RuntimeError(
        "No se encontró modelo en Registry ni pickle local. "
        f"Configurá MLFLOW_TRACKING_URI o verificá que exista {MODEL_PATH}."
    )
