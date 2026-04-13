"""
FastAPI — PMT MLSec Model A Inference API

Endpoint principal: POST /predict
Dado un request HTTP, clasifica si es ataque (1) o normal (0).

Uso en Docker:
    docker compose -f docker/docker-compose.yml up api
    → http://localhost:5000/docs

Variables de entorno:
    MODEL_PATH          — path al pickle del modelo (default: models/model_a_lightgbm.pkl)
    MLFLOW_TRACKING_URI — servidor MLflow para cargar desde artefacto
    THRESHOLD          — override del threshold (default: 0.2903)
    HOST               — host del servidor (default: 0.0.0.0)
    PORT               — puerto (default: 5000)
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from mlsec.api.models import (
    FEATURE_NAMES,
    PredictRequest,
    PredictResponse,
    HealthResponse,
)
from mlsec.api.model_loader import (
    get_model,
    THRESHOLD as DEFAULT_THRESHOLD,
    MODEL_VERSION,
)

# ---------------------------------------------------------------------------
# Estado global — se carga una sola vez al arrancar
# ---------------------------------------------------------------------------
model = None
scaler = None
threshold = DEFAULT_THRESHOLD
model_load_error: str | None = None


def load_model_once():
    global model, scaler, threshold, model_load_error
    try:
        model, scaler, threshold = get_model()
        print(f"Modelo cargado. Threshold: {threshold}")
    except Exception as exc:  # noqa: BLE001
        model_load_error = str(exc)
        print(f"ERROR cargando modelo: {exc}", file=sys.stderr)
        print("API arrancará en modo degraded (/predict responderá con 503)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model_once()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PMT MLSec — Model A Inference API",
    description=(
        "Clasificación de requests HTTP como ataque (1) o normal (0) "
        "usando el modelo LightGBM entrenado sobre CSIC 2010."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — permitir cualquier origen en dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    """Verifica que la API está viva y si el modelo está cargado."""
    if model_load_error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "model_loaded": False,
                "model_version": None,
            },
        )
    return HealthResponse(
        status="ok",
        model_loaded=True,
        model_version=MODEL_VERSION,
    )


# ---------------------------------------------------------------------------
# GET /features — info sobre las features esperadas
# ---------------------------------------------------------------------------
@app.get("/features", tags=["model"])
async def list_features():
    """Lista las 23 features que el modelo espera, en orden."""
    return {
        "count": len(FEATURE_NAMES),
        "features": FEATURE_NAMES,
        "threshold": threshold,
        "model_version": MODEL_VERSION,
    }


# ---------------------------------------------------------------------------
# POST /predict
# ---------------------------------------------------------------------------
@app.post("/predict", response_model=PredictResponse, tags=["inference"])
async def predict(req: PredictRequest):
    """
    Clasifica un request HTTP.

    - **prediction**: 0 = normal, 1 = ataque
    - **probability**: P(ataque) según el modelo
    - **threshold**: valor usado para la decisión
    """
    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"Modelo no disponible: {model_load_error}",
        )

    import numpy as np

    # LightGBM no requiere scaling — es invariante a transformaciones monótonas
    features = np.array([req.to_array()], dtype="float32")
    proba = float(model.predict_proba(features)[:, 1][0])
    prediction = int(proba >= threshold)

    return PredictResponse(
        prediction=prediction,
        probability=round(proba, 4),
        threshold=threshold,
        model_version=MODEL_VERSION,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    uvicorn.run(app, host=host, port=port)
