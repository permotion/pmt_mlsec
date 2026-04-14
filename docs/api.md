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

## Feature extraction — de HTTP request a 23 features

Esta sección documenta exactamente cómo computar cada una de las 23 features a partir de un request HTTP crudo (method, URL, body). Toda la lógica replica `src/mlsec/data/preprocess_csic_v4.py`, que fue validada contra el dataset CSIC 2010 durante las iteraciones de feature engineering.

### Flujo de parsing

```
HTTP Request crudo
├── Method  →  method_is_get / method_is_post / method_is_put
├── URL     →  url_length / url_param_count / url_pct_density
│               url_path_depth / url_query_length / url_has_query
│               url_has_pct27 / url_has_pct3c / url_has_dashdash
│               url_has_script / url_has_select
└── Body    →  content_length / content_pct_density
                content_param_count / content_param_density
                content_has_pct27 / content_has_pct3c / content_has_dashdash
                content_has_script / content_has_select
```

---

### Paso 1 — Method encoding

```python
def encode_method(method: str) -> tuple[int, int, int]:
    """
    One-hot encoding del método HTTP.

    Args:
        method: método HTTP en texto (ej: "GET", "POST", "PUT")

    Returns:
        (method_is_get, method_is_post, method_is_put)
        Cada valor es 1 si ese es el método, 0 si no.
    """
    m = method.upper()
    return (
        1 if m == "GET"  else 0,
        1 if m == "POST" else 0,
        1 if m == "PUT"  else 0,
    )
```

| Método del request | method_is_get | method_is_post | method_is_put |
|---|---|---|---|
| GET / HEAD / DELETE / etc. | 1 | 0 | 0 |
| POST | 0 | 1 | 0 |
| PUT | 0 | 0 | 1 |

**Nota:** en CSIC 2010, PUT tiene 100% de ataques — esta es la feature más discriminativa del dataset. DELETE y HEAD no existen en el training set.

---

### Paso 2 — URL features

#### 2a. Features estructurales

```python
from urllib.parse import urlparse

def build_url_structural(url: str) -> dict:
    """
    Extrae features estructurales de la URL.

    Estructura de una URL:
        scheme://netloc/path;params?query#fragment
    """
    # Dividir en path y query string en el primer '?'
    path_plus_query = url.split("?", 1)
    path            = path_plus_query[0]
    query           = path_plus_query[1] if len(path_plus_query) > 1 else ""

    return {
        "url_length":        len(url),
        "url_param_count":   url.count("="),         # '=' en toda la URL
        "url_pct_density":   url.count("%") / max(len(url), 1),
        "url_path_depth":     path.count("/"),        # cantidad de '/' en el path
        "url_query_length":  len(query),
        "url_has_query":     1 if "?" in url else 0,
    }
```

| Feature | Cómo se computa | Ejemplo |
|---|---|---|
| `url_length` | `len(url)` | `/api/search?q=test&page=1` → 23 |
| `url_param_count` | `url.count("=")` | Cuenta todos los `=` en la URL completa, incluyendo query string |
| `url_pct_density` | `url.count("%") / len(url)` | `%` codifica caracteres especiales en ataques SQLi/XSS |
| `url_path_depth` | `path.count("/")` | `/a/b/c` → 3 (3 separadores de segmento) |
| `url_query_length` | `len(query_string)` | Solo lo que va después del `?` |
| `url_has_query` | `1 if "?" in url else 0` | Indica si la URL tiene query string |

**Ejemplo paso a paso:**

```
URL:  /dvwa/vulnerabilities/sqli/?id=%27&Submit=Submit
       ─────────────── ─────────────────────────────
       path              query string

url_length        = 56
url_param_count    = 2        (id=, Submit=)
url_pct_density    = 3 / 56   = 0.0536
url_path_depth      = 3        (/dvwa, /vulnerabilities, /sqli)
url_query_length    = 28
url_has_query       = 1
```

#### 2b. Indicadores de texto en URL

```python
TEXT_INDICATORS = {
    "pct27":    "%27",    # encoding de comilla simple (')
    "pct3c":    "%3C",    # encoding de '<'
    "dashdash": "--",     # comentario SQL
    "script":   "script", # XSS con etiquetas <script>
    "select":   "SELECT", # keyword SQL (case-insensitive)
}

def build_url_text_indicators(url: str) -> dict:
    """Detecta patrones de ataque en la URL (case-insensitive)."""
    url_lower = url.lower()
    return {
        f"url_has_{name}": 1 if pattern.lower() in url_lower else 0
        for name, pattern in TEXT_INDICATORS.items()
    }
```

| Pattern | Qué detecta | Ejemplo malicioso |
|---|---|---|
| `%27` | Comilla simple URL-encodeda | `/?id=%27%20OR%201=1` |
| `%3C` | `<` URL-encodeda | `/search?q=%3Cscript%3E` |
| `--` | Comentario SQL | `/?id=1%20--` |
| `script` | Etiqueta `<script>` en texto plano | `/xss?q=<script>alert(1)</script>` |
| `SELECT` | Keyword SQL (case-insensitive) | `/search?q=SELECT%20*%20FROM%20users` |

!!! warning "URL encoding vs texto plano"
    Los atacantes en CSIC 2010 **siempre** usan URL encoding para patrones SQLi/XSS.
    Nunca usan `'`, `<` en texto literal — siempre `%27`, `%3C`.
    Esto hace que `url_has_pct27` sea más confiable que buscar `'`.

---

### Paso 3 — Content/Body features

```python
def build_content_features(body: str) -> dict:
    """
    Extrae features del body del request HTTP.

    Args:
        body: contenido del body, o string vacío para GET.
              Puede venir en el header Content-Length o en el body HTTP.
    """
    content = body if body else ""

    length   = len(content)
    clipped  = max(length, 1)   # evitar división por cero

    return {
        "content_length":         length,
        "content_pct_density":    content.count("%") / clipped,
        "content_param_count":    content.count("="),
        "content_param_density":   content.count("=") / clipped,
    }
```

| Feature | Cómo se computa | Ejemplo ataque | Ejemplo normal |
|---|---|---|---|
| `content_length` | `len(body)` | Payload largo inyectado | Formulario de login corto |
| `content_pct_density` | `body.count("%") / max(len(body), 1)` | `%27%20OR%201=1` → alta densidad de `%` | `username=tom&password=1234` → 0 |
| `content_param_count` | `body.count("=")` | `id=%27%20OR%201=1&Submit=` → 2 | `username=tom&password=1234` → 2 |
| `content_param_density` | `param_count / max(content_length, 1)` | Payload largo / pocos `=` → valor bajo | Formulario corto / muchos `=` → valor alto |

**Ejemplo:**

```
# Request POST normal
body:  username=tom&password=1234&Submit=Login
       ───────────────────────────────────────
       content_length       = 37
       content_param_count  = 3
       content_param_density = 3 / 37 = 0.081
       content_pct_density  = 0

# Request POST malicioso (SQLi)
body:  id=%27%20OR%20%271%27%3D%271&Submit=Submit
       ─────────────────────────────────────────
       content_length       = 44
       content_param_count  = 2
       content_param_density = 2 / 44 = 0.045   ← menor que el normal
       content_pct_density  = 9 / 44 = 0.205   ← indicador de encoding
```

#### Indicadores de texto en body

```python
def build_content_text_indicators(body: str) -> dict:
    """Detecta patrones de ataque en el body (case-insensitive)."""
    content_lower = (body if body else "").lower()
    return {
        f"content_has_{name}": 1 if pattern.lower() in content_lower else 0
        for name, pattern in TEXT_INDICATORS.items()
    }
```

Los mismos 5 patrones que en URL (`pct27`, `pct3c`, `dashdash`, `script`, `select`) se buscan en el body.

---

### Función completa — `extract_features()`

```python
from urllib.parse import urlparse

TEXT_INDICATORS = {
    "pct27":    "%27",
    "pct3c":    "%3C",
    "dashdash": "--",
    "script":   "script",
    "select":   "SELECT",
}


def extract_features(method: str, url: str, body: str | None = None) -> list[float]:
    """
    Convierte un HTTP request a las 23 features del modelo.

    Args:
        method: método HTTP (GET, POST, PUT, etc.)
        url:    URL completa (con o sin scheme)
        body:   body del request (None o "" para GET)

    Returns:
        Lista ordenada de 23 floats — el orden es el de FEATURE_NAMES.

    Ejemplo de uso:
        >>> features = extract_features(
        ...     method="POST",
        ...     url="/dvwa/vulnerabilities/sqli/?id=%27&Submit=Submit",
        ...     body="username=admin&password=%27%20OR%201=1"
        ... )
        >>> print(len(features))
        23
    """
    m = method.upper()
    method_is_get  = 1 if m == "GET"  else 0
    method_is_post = 1 if m == "POST" else 0
    method_is_put  = 1 if m == "PUT"  else 0

    # URL
    path_plus_query = url.split("?", 1)
    path   = path_plus_query[0]
    query  = path_plus_query[1] if len(path_plus_query) > 1 else ""
    url_lower = url.lower()

    url_length        = len(url)
    url_param_count   = url.count("=")
    url_pct_density   = url.count("%") / max(len(url), 1)
    url_path_depth    = path.count("/")
    url_query_length  = len(query)
    url_has_query     = 1 if "?" in url else 0
    url_has_pct27     = 1 if "%27"  in url else 0
    url_has_pct3c     = 1 if "%3C"  in url else 0
    url_has_dashdash  = 1 if "--"   in url_lower else 0
    url_has_script    = 1 if "script" in url_lower else 0
    url_has_select    = 1 if "select" in url_lower else 0

    # Body
    content       = body if body else ""
    content_lower = content.lower()
    cl            = len(content)
    cl_clip       = max(cl, 1)

    content_length        = cl
    content_pct_density   = content.count("%") / cl_clip
    content_param_count   = content.count("=")
    content_param_density = content.count("=") / cl_clip
    content_has_pct27     = 1 if "%27"  in content else 0
    content_has_pct3c     = 1 if "%3C"  in content else 0
    content_has_dashdash  = 1 if "--"   in content_lower else 0
    content_has_script    = 1 if "script" in content_lower else 0
    content_has_select    = 1 if "select" in content_lower else 0

    return [
        # Method (3)
        method_is_get, method_is_post, method_is_put,
        # URL structural (6)
        url_length, url_param_count, url_pct_density,
        url_path_depth, url_query_length, url_has_query,
        # URL text indicators (5)
        url_has_pct27, url_has_pct3c, url_has_dashdash,
        url_has_script, url_has_select,
        # Body structural (4)
        content_length, content_pct_density,
        content_param_count, content_param_density,
        # Body text indicators (5)
        content_has_pct27, content_has_pct3c, content_has_dashdash,
        content_has_script, content_has_select,
    ]
```

---

### Casos borde

| Caso | Comportamiento |
|---|---|
| `body = None` o `body = ""` | Treats as empty string — `content_length=0`, todas las densities = 0 |
| URL sin `?` | `url_query_length=0`, `url_has_query=0`, query string tratada como vacía |
| Path sin `/` | `url_path_depth=0` (ej: `/login` → 1) |
| `content_length = 0` | `content_param_density = 0` (usamos `max(len, 1)` como denominador) |
| Case en `script` / `SELECT` | Se compara en lowercase — `SELECT`, `Select`, `select` dan `content_has_select=1` |
| `%` literal en URL (no encoding) | Se cuenta igual que `%3C` — puede dar falsos positivos en URLs legítimas con `%20` encoding |

---

### Ejemplo end-to-end

```python
# Request malicioso
method = "POST"
url    = "/dvwa/vulnerabilities/sqli/?id=%27%20OR%201%3D1&Submit=Submit"
body   = "username=admin&password=%27%20OR%20%271%27%3D%271"

features = extract_features(method, url, body)
# Resultado:
# [0, 1, 0,           # method: POST
#  56, 2, 0.0536,      # url structural
#  3, 28, 1,           # url query
#  1, 1, 0, 0, 0,      # url text: %27 ✅ %3C ✅
#  44, 0.2045, 2, 0.045,  # body structural
#  1, 1, 0, 0, 0]     # body text: %27 ✅ %3C ✅

# Request normal
method = "GET"
url    = "/api/users/123"
body   = ""

features = extract_features(method, url, body)
# Resultado:
# [1, 0, 0,           # method: GET
#  12, 1, 0.0,        # url structural
#  2, 0, 0,           # url query: /api/users/123 → depth=3
#  0, 0, 0, 0, 0,     # url text: sin indicadores
#  0, 0.0, 0, 0.0,    # body: vacío
#  0, 0, 0, 0, 0]     # body text: todo 0
```

---

### Cómo usar esto en la práctica

Si necesitás extraer features desde requests HTTP reales (logs de un proxy, tráfico capturado, etc.):

```python
# Ejemplo con un log de Nginx
log_line = '127.0.0.1 - - [13/Apr/2026:10:00:00 +0000] ' \
            '"POST /dvwa/vulnerabilities/sqli/?id=%27 HTTP/1.1" 200 1234'

# Parsear método y URL del log (formato: "METHOD /path?query HTTP/1.1")
parts = log_line.split('"')[1].split()
method = parts[0]
url    = parts[1]

# Llamar a la extract_features
features = extract_features(method, url, body=None)
```

Para requests POST con body real, el body se obtiene del payload HTTP.

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
