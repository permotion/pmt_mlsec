# FastAPI — Inference API

Endpoint REST para clasificar requests HTTP como ataque (1) o normal (0) usando el modelo LightGBM de Model A.

**En producción (Docker):** `http://localhost:5082`
**UI de docs interactiva:** `http://localhost:5082/docs`
**Health:** `http://localhost:5082/health`

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    docker-compose                           │
│                                                             │
│   ┌──────────┐   ┌───────────┐   ┌───────────────────────┐  │
│   │  mlflow  │──▶│   api    │──▶│  LightGBM (descargado│  │
│   │ :5000   │   │  :5082   │   │  desde artefacto)     │  │
│   └──────────┘   └───────────┘   └───────────────────────┘  │
│   artefacto del     FastAPI +                     Modelo    │
│   modelo guardado   Pydantic                     listo     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

El contenedor de la API se conecta al servidor MLflow (`http://mlflow:5000`) al arrancar, busca el run con mejor Recall del experimento `mlsec-model-a`, descarga el artefacto `model/` y carga el modelo en memoria. Todo esto pasa una sola vez en startup.

---

## Cómo levantar

```bash
# Todos los servicios (postgres + mlflow + airflow + api)
cd docker && docker compose up

# Solo la API (requiere mlflow corriendo)
docker compose -f docker/docker-compose.yml up api
```

**Servicios disponibles:**

| Servicio | Puerto | URL |
|---|---|---|
| API | 5082 | http://localhost:5082/docs |
| Airflow | 5080 | http://localhost:5080 |
| MLflow | 5081 | http://localhost:5081 |

---

## Endpoints

### `GET /health`

Verifica que la API está viva y el modelo está cargado.

```bash
curl http://localhost:5082/health
```

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "v1-dag-2026-04-13"
}
```

| Estado | Significado |
|---|---|
| `ok` | API viva + modelo cargado ✅ |
| `degraded` | API viva pero modelo no cargó ❌ (ver logs del contenedor) |

---

### `GET /features`

Lista las 23 features que el modelo espera, en orden exacto.

```bash
curl http://localhost:5082/features
```

```json
{
  "count": 23,
  "features": [
    "method_is_get", "method_is_post", "method_is_put",
    "url_length", "url_param_count", "url_pct_density",
    "url_path_depth", "url_query_length", "url_has_query",
    "url_has_pct27", "url_has_pct3c", "url_has_dashdash",
    "url_has_script", "url_has_select",
    "content_length", "content_pct_density",
    "content_param_count", "content_param_density",
    "content_has_pct27", "content_has_pct3c", "content_has_dashdash",
    "content_has_script", "content_has_select"
  ],
  "threshold": 0.2903,
  "model_version": "v1-dag-2026-04-13"
}
```

!!! warning "Orden de las features importa"
    El array de features debe enviarse en este orden exacto. Cada posición corresponde a la columna del parquet de entrenamiento.

---

### `POST /predict`

Clasifica un request HTTP.

```bash
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d '{
    "method_is_get": 1,
    "method_is_post": 0,
    "method_is_put": 0,
    "url_length": 45,
    "url_param_count": 0,
    "url_pct_density": 0,
    "url_path_depth": 2,
    "url_query_length": 0,
    "url_has_query": 0,
    "url_has_pct27": 0,
    "url_has_pct3c": 0,
    "url_has_dashdash": 0,
    "url_has_script": 0,
    "url_has_select": 0,
    "content_length": 0,
    "content_pct_density": 0,
    "content_param_count": 0,
    "content_param_density": 0,
    "content_has_pct27": 0,
    "content_has_pct3c": 0,
    "content_has_dashdash": 0,
    "content_has_script": 0,
    "content_has_select": 0
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
| `threshold` | Umbral usado para la decisión (`0.2903`) |
| `model_version` | Tag del modelo cargado |

---

## Features — referencia completa

### Binarias (0 o 1)

| Feature | Descripción |
|---|---|
| `method_is_get` | Request GET |
| `method_is_post` | Request POST |
| `method_is_put` | Request PUT — 100% ataques en CSIC 2010 |
| `url_has_query` | URL tiene query string (`?`) |
| `url_has_pct27` | `%27` en URL (encoding de `'`) |
| `url_has_pct3c` | `%3C` en URL (encoding de `<`) |
| `url_has_dashdash` | `--` en URL |
| `url_has_script` | `script` en URL |
| `url_has_select` | `select` en URL |
| `content_has_pct27` | `%27` en body |
| `content_has_pct3c` | `%3C` en body |
| `content_has_dashdash` | `--` en body |
| `content_has_script` | `script` en body |
| `content_has_select` | `select` en body |

### Continuas (valores numéricos)

| Feature | Tipo | Descripción |
|---|---|---|
| `url_length` | int | Longitud total de la URL |
| `url_param_count` | int | Cantidad de parámetros en la query string |
| `url_pct_density` | float | Densidad de `%` en la URL |
| `url_path_depth` | int | Profundidad del path (`/` segments) |
| `url_query_length` | int | Longitud del query string |
| `content_length` | int | Longitud del body (0 para GET) |
| `content_pct_density` | float | Densidad de `%` en el body |
| `content_param_count` | int | Cantidad de `=` en el body |
| `content_param_density` | float | `content_param_count / content_length` |

---

## Preprocessing en la API

El modelo fue entrenado con **StandardScaler** aplicado a 3 features continuas. La API aplica la misma transformación con parámetros hardcodeados (fit en train set original):

| Feature | Mean | Std |
|---|---|---|
| `url_length` | 90.32 | 75.49 |
| `url_query_length` | 33.95 | 77.81 |
| `content_length` | 31.96 | 76.05 |

```python
# src/mlsec/api/preprocessing.py
for i, col in enumerate(CONTINUOUS_COLS):
    idx = feature_names.index(col)
    features[0, idx] = (features[0, idx] - SCALER_MEAN[i]) / SCALER_STD[i]
```

Las features binarias no se transforman.

---

## Modelo y threshold

### Modelo

- **Algoritmo:** LightGBM
- **Dataset:** CSIC 2010 (61.065 requests, 41% ataques)
- **Features:** 23 (v4)
- **n_estimators:** 200
- **Artefacto guardado con:** `mlflow.sklearn.log_model()`
- **Ubicación:** MLflow server → experimento `mlsec-model-a` → último run → artifact `model/`

### Threshold

El threshold de decisión es **0.2903** — no 0.5.

Este valor fue calibrado en el task `train` del DAG para maximizar Precision manteniendo Recall ≥ 0.955 en el validation set. El resultado de esa calibración es que:

- **Cualquier probabilidad ≥ 0.2903 → attack (1)**
- **Cualquier probabilidad < 0.2903 → normal (0)**

### Sobre las probabilidades absolutas

!!! warning "Probabilidades sesgadas por scale_pos_weight"
    El modelo fue entrenado con `scale_pos_weight = neg/pos ≈ 1.44` (el dataset tiene 59% normales / 41% ataques). Esto sesga las probabilidades hacia la clase minoritaria (ataque) y hace que las probabilidades absolutas sean difíciles de interpretar.

    Un request normal puede devolver `probability=0.98` no porque el modelo esté seguro de que es ataque, sino porque el `scale_pos_weight` infló artificialmente la probabilidad de la clase positiva.

    El threshold de 0.2903 compensa parcialmente esto — fue calibrado específicamente para el nivel de recall objetivo. No es equivalente a threshold=0.5 de un modelo sin reweighting.

**En la práctica:** interpretar la `prediction` (0/1) como decisión final, y la `probability` como indicador de confianza relativo dentro del modelo. No usar la probabilidad absoluta como score directamente.

---

## Carga del modelo

```
1. Revisa MODEL_PATH (env var) → archivo pickle local
2. Si no existe → usa MLFLOW_TRACKING_URI → conecta al servidor MLflow
3. Busca el run con mejor test_recall en experimento mlsec-model-a
4. Descarga artefacto model/ desde artifact_uri
5. Carga model.pkl en memoria
```

Si nada está disponible → modo `degraded` (`/health` responde 503, `/predict` responde 500).

### Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | Servidor MLflow para descargar el modelo |
| `MODEL_PATH` | `models/model_a_lightgbm.pkl` | Path local al pickle del modelo |
| `HOST` | `0.0.0.0` | Host del servidor |
| `PORT` | `5082` | Puerto del servidor |

---

## Estructura de archivos

```
src/mlsec/api/
├── __init__.py
├── main.py              ← FastAPI app (endpoints)
├── models.py           ← Pydantic schemas (PredictRequest, PredictResponse)
├── model_loader.py     ← Carga del modelo desde pickle o MLflow
└── preprocessing.py    ← StandardScaler con parámetros hardcodeados

docker/
├── Dockerfile.api      ← Imagen python:3.11-slim + libgomp1 + deps
├── docker-compose.yml  ← Servicio api en puerto 5082
└── ...                 ← MLflow, Airflow, Postgres

requirements-api.txt    ← fastapi, uvicorn, pydantic, lightgbm, mlflow, etc.
```

---

## Errores conocidos

### `scale_pos_weight` infla las probabilidades

Un request normal puede devolver probabilidad 0.98. Esto es esperado — el modelo fue entrenado para maximizar recall, no calibrar probabilidades absolutas. Usar `prediction` para la decisión binaria.

### `model_loaded: false` en /health

Ver los logs del contenedor:
```bash
docker logs pmtmlsec-api-1
```
Causas comunes:
- `libgomp.so.1` no instalado → rebuild con `docker compose build api`
- MLflow no accesible desde la API → verificar `MLFLOW_TRACKING_URI`
- Run del modelo no encontrado → verificar que el DAG corrió al menos una vez
