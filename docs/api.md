# FastAPI — Inference API

Endpoint REST para clasificar requests HTTP como ataque (1) o normal (0) usando el modelo LightGBM de Model A.

**En producción (Docker):** `http://localhost:5000`  
**UI de docs interactiva:** `http://localhost:5000/docs`

---

## Endpoints

### `GET /health`

Verifica que la API está viva y el modelo está cargado.

```bash
curl http://localhost:5000/health
```

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "v1-dag-2026-04-13"
}
```

Si el modelo no está disponible, responde con `503 degraded`.

---

### `GET /features`

Lista las 23 features que el modelo espera, en orden.

```bash
curl http://localhost:5000/features
```

```json
{
  "count": 23,
  "features": ["url_length", "url_query_length", ...],
  "threshold": 0.2903,
  "model_version": "v1-dag-2026-04-13"
}
```

---

### `POST /predict`

Clasifica un request HTTP.

```bash
curl -X POST http://localhost:5000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "url_length": 127,
    "url_query_length": 89,
    "content_length": 0,
    "method_is_get": 1,
    "method_is_post": 0,
    "method_is_put": 0,
    "url_pct27": 0,
    "url_pct3c": 0,
    "url_pct20": 1,
    "url_dashdash": 0,
    "url_script": 0,
    "url_select": 0,
    "url_union": 0,
    "url_or": 0,
    "url_and": 0,
    "content_param_count": 0,
    "content_param_density": 0,
    "content_pct27": 0,
    "content_pct3c": 0,
    "content_pct20": 0,
    "content_dashdash": 0,
    "content_script": 0,
    "url_pct_density": 0.03
  }'
```

```json
{
  "prediction": 0,
  "probability": 0.0812,
  "threshold": 0.2903,
  "model_version": "v1-dag-2026-04-13"
}
```

| Campo | Descripción |
|---|---|
| `prediction` | `0` = normal, `1` = ataque |
| `probability` | `P(ataque)` según LightGBM |
| `threshold` | Umbral usado para decidir (0.2903) |
| `model_version` | Tag del modelo cargado |

---

## Cómo levantar

```bash
# Con Docker Compose (todos los servicios)
cd docker && docker compose up

# Solo la API (requiere que MLflow esté corriendo)
docker compose -f docker/docker-compose.yml up api
```

**Servicios disponibles:**

| Servicio | Puerto | URL |
|---|---|---|
| API | 5000 | http://localhost:5000/docs |
| Airflow | 5080 | http://localhost:5080 |
| MLflow | 5081 | http://localhost:5081 |

---

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | Servidor MLflow para cargar el modelo |
| `MODEL_PATH` | `models/model_a_lightgbm.pkl` | Path local al pickle del modelo |
| `THRESHOLD` | `0.2903` | Override del threshold |
| `HOST` | `0.0.0.0` | Host del servidor |
| `PORT` | `5000` | Puerto del servidor |

---

## Carga del modelo

El modelo se carga en startup (una sola vez):

1. Si `MODEL_PATH` existe → carga desde pickle local
2. Si `MLFLOW_TRACKING_URI` está seteado → descarga el artefacto del último run de `mlsec-model-a`
3. Si nada está disponible → la API arranca en modo `degraded` (`/predict` responde 503)

---

## Estructura de archivos

```
src/mlsec/api/
├── __init__.py
├── main.py          ← FastAPI app
├── models.py        ← Pydantic schemas (PredictRequest, PredictResponse)
└── model_loader.py  ← Carga del modelo desde pickle o MLflow

docker/
├── Dockerfile.api        # imagen FastAPI
├── requirements-api.txt  # dependencias de la API
└── docker-compose.yml    # incluye servicio api
```
