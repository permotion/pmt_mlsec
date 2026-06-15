# FastAPI — Inference API

REST endpoint to classify HTTP requests as attack (1) or normal (0) using Model A's LightGBM model.

**In production (Docker):** `http://localhost:5082`
**Interactive docs UI:** `http://localhost:5082/docs`
**Health:** `http://localhost:5082/health`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    docker-compose                           │
│                                                             │
│   ┌──────────┐   ┌───────────┐   ┌───────────────────────┐  │
│   │  mlflow  │──▶│   api    │──▶│  LightGBM (downloaded  │  │
│   │ :5000   │   │  :5082   │   │  from artifact)       │  │
│   └──────────┘   └───────────┘   └───────────────────────┘  │
│   saved model      FastAPI +                     Ready     │
│   artifact         Pydantic                      Model     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

The API container connects to the MLflow server (`http://mlflow:5000`) on startup, looks for the run with the best Recall in the `mlsec-model-a` experiment, downloads the `model/` artifact, and loads the model into memory. All this happens only once at startup.

---

## How to start

```bash
# All services (postgres + mlflow + airflow + api)
cd docker && docker compose up

# Only the API (requires mlflow running)
docker compose -f docker/docker-compose.yml up api
```

**Available services:**

| Service | Port | URL |
|---|---|---|
| API | 5082 | http://localhost:5082/docs |
| Airflow | 5080 | http://localhost:5080 |
| MLflow | 5081 | http://localhost:5081 |

---

## Endpoints

### `GET /health`

Verifies that the API is alive and the model is loaded.

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

| Status | Meaning |
|---|---|
| `ok` | API alive + model loaded ✅ |
| `degraded` | API alive but model failed to load ❌ (check container logs) |

---

### `GET /features`

Lists the 23 features the model expects, in exact order.

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

!!! warning "Feature order matters"
    The features array must be sent in this exact order. Each position corresponds to the training parquet column.

---

### `POST /predict`

Classifies an HTTP request.

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

| Field | Description |
|---|---|
| `prediction` | `0` = normal, `1` = attack |
| `probability` | `P(attack)` according to LightGBM |
| `threshold` | Threshold used for the decision (`0.2903`) |
| `model_version` | Tag of the loaded model |

---

## Feature extraction — from HTTP request to 23 features

This section documents exactly how to compute each of the 23 features from a raw HTTP request (method, URL, body). All logic replicates `src/mlsec/data/preprocess_csic_v4.py`, which was validated against the CSIC 2010 dataset during feature engineering iterations.

### Parsing flow

```
Raw HTTP Request
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

### Step 1 — Method encoding

```python
def encode_method(method: str) -> tuple[int, int, int]:
    """
    One-hot encoding of the HTTP method.

    Args:
        method: HTTP method in text (e.g., "GET", "POST", "PUT")

    Returns:
        (method_is_get, method_is_post, method_is_put)
        Each value is 1 if that is the method, 0 otherwise.
    """
    m = method.upper()
    return (
        1 if m == "GET"  else 0,
        1 if m == "POST" else 0,
        1 if m == "PUT"  else 0,
    )
```

| Request Method | method_is_get | method_is_post | method_is_put |
|---|---|---|---|
| GET / HEAD / DELETE / etc. | 1 | 0 | 0 |
| POST | 0 | 1 | 0 |
| PUT | 0 | 0 | 1 |

**Note:** in CSIC 2010, PUT has 100% attacks — this is the most discriminative feature in the dataset. DELETE and HEAD do not exist in the training set.

---

### Step 2 — URL features

#### 2a. Structural features

```python
from urllib.parse import urlparse

def build_url_structural(url: str) -> dict:
    """
    Extracts structural features from the URL.

    URL structure:
        scheme://netloc/path;params?query#fragment
    """
    # Split into path and query string at the first '?'
    path_plus_query = url.split("?", 1)
    path            = path_plus_query[0]
    query           = path_plus_query[1] if len(path_plus_query) > 1 else ""

    return {
        "url_length":        len(url),
        "url_param_count":   url.count("="),         # '=' in entire URL
        "url_pct_density":   url.count("%") / max(len(url), 1),
        "url_path_depth":     path.count("/"),        # number of '/' in the path
        "url_query_length":  len(query),
        "url_has_query":     1 if "?" in url else 0,
    }
```

| Feature | How it is computed | Example |
|---|---|---|
| `url_length` | `len(url)` | `/api/search?q=test&page=1` → 23 |
| `url_param_count` | `url.count("=")` | Counts all `=` in the full URL, including query string |
| `url_pct_density` | `url.count("%") / len(url)` | `%` encodes special characters in SQLi/XSS attacks |
| `url_path_depth` | `path.count("/")` | `/a/b/c` → 3 (3 segment separators) |
| `url_query_length` | `len(query_string)` | Only what comes after `?` |
| `url_has_query` | `1 if "?" in url else 0` | Indicates if URL has a query string |

**Step by step example:**

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

#### 2b. URL text indicators

```python
TEXT_INDICATORS = {
    "pct27":    "%27",    # single quote encoding (')
    "pct3c":    "%3C",    # '<' encoding
    "dashdash": "--",     # SQL comment
    "script":   "script", # XSS with <script> tags
    "select":   "SELECT", # SQL keyword (case-insensitive)
}

def build_url_text_indicators(url: str) -> dict:
    """Detects attack patterns in the URL (case-insensitive)."""
    url_lower = url.lower()
    return {
        f"url_has_{name}": 1 if pattern.lower() in url_lower else 0
        for name, pattern in TEXT_INDICATORS.items()
    }
```

| Pattern | What it detects | Malicious example |
|---|---|---|
| `%27` | URL-encoded single quote | `/?id=%27%20OR%201=1` |
| `%3C` | URL-encoded `<` | `/search?q=%3Cscript%3E` |
| `--` | SQL comment | `/?id=1%20--` |
| `script` | Plaintext `<script>` tag | `/xss?q=<script>alert(1)</script>` |
| `SELECT` | SQL keyword (case-insensitive) | `/search?q=SELECT%20*%20FROM%20users` |

!!! warning "URL encoding vs plain text"
    Attackers in CSIC 2010 **always** use URL encoding for SQLi/XSS patterns.
    They never use literal `'`, `<` — always `%27`, `%3C`.
    This makes `url_has_pct27` more reliable than looking for `'`.

---

### Step 3 — Content/Body features

```python
def build_content_features(body: str) -> dict:
    """
    Extracts features from the HTTP request body.

    Args:
        body: body content, or empty string for GET.
              Can come from Content-Length header or HTTP body.
    """
    content = body if body else ""

    length   = len(content)
    clipped  = max(length, 1)   # avoid division by zero

    return {
        "content_length":         length,
        "content_pct_density":    content.count("%") / clipped,
        "content_param_count":    content.count("="),
        "content_param_density":   content.count("=") / clipped,
    }
```

| Feature | How it is computed | Attack example | Normal example |
|---|---|---|---|
| `content_length` | `len(body)` | Long injected payload | Short login form |
| `content_pct_density` | `body.count("%") / max(len(body), 1)` | `%27%20OR%201=1` → high `%` density | `username=tom&password=1234` → 0 |
| `content_param_count` | `body.count("=")` | `id=%27%20OR%201=1&Submit=` → 2 | `username=tom&password=1234` → 2 |
| `content_param_density` | `param_count / max(content_length, 1)` | Long payload / few `=` → low value | Short form / many `=` → high value |

**Example:**

```
# Normal POST request
body:  username=tom&password=1234&Submit=Login
       ───────────────────────────────────────
       content_length       = 37
       content_param_count  = 3
       content_param_density = 3 / 37 = 0.081
       content_pct_density  = 0

# Malicious POST request (SQLi)
body:  id=%27%20OR%20%271%27%3D%271&Submit=Submit
       ─────────────────────────────────────────
       content_length       = 44
       content_param_count  = 2
       content_param_density = 2 / 44 = 0.045   ← lower than normal
       content_pct_density  = 9 / 44 = 0.205   ← encoding indicator
```

#### Body text indicators

```python
def build_content_text_indicators(body: str) -> dict:
    """Detects attack patterns in the body (case-insensitive)."""
    content_lower = (body if body else "").lower()
    return {
        f"content_has_{name}": 1 if pattern.lower() in content_lower else 0
        for name, pattern in TEXT_INDICATORS.items()
    }
```

The same 5 patterns as in URL (`pct27`, `pct3c`, `dashdash`, `script`, `select`) are searched for in the body.

---

### Complete function — `extract_features()`

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
    Converts an HTTP request to the 23 model features.

    Args:
        method: HTTP method (GET, POST, PUT, etc.)
        url:    Full URL (with or without scheme)
        body:   Request body (None or "" for GET)

    Returns:
        Ordered list of 23 floats — order matches FEATURE_NAMES.

    Usage example:
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

### Edge cases

| Case | Behavior |
|---|---|
| `body = None` or `body = ""` | Treats as empty string — `content_length=0`, all densities = 0 |
| URL without `?` | `url_query_length=0`, `url_has_query=0`, query string treated as empty |
| Path without `/` | `url_path_depth=0` (e.g., `/login` → 1) |
| `content_length = 0` | `content_param_density = 0` (we use `max(len, 1)` as denominator) |
| Case in `script` / `SELECT` | Compared in lowercase — `SELECT`, `Select`, `select` yield `content_has_select=1` |
| Literal `%` in URL (no encoding) | Counted same as `%3C` — can yield false positives in legitimate URLs with `%20` encoding |

---

### End-to-end example

```python
# Malicious request
method = "POST"
url    = "/dvwa/vulnerabilities/sqli/?id=%27%20OR%201%3D1&Submit=Submit"
body   = "username=admin&password=%27%20OR%20%271%27%3D%271"

features = extract_features(method, url, body)
# Result:
# [0, 1, 0,           # method: POST
#  56, 2, 0.0536,      # url structural
#  3, 28, 1,           # url query
#  1, 1, 0, 0, 0,      # url text: %27 ✅ %3C ✅
#  44, 0.2045, 2, 0.045,  # body structural
#  1, 1, 0, 0, 0]     # body text: %27 ✅ %3C ✅

# Normal request
method = "GET"
url    = "/api/users/123"
body   = ""

features = extract_features(method, url, body)
# Result:
# [1, 0, 0,           # method: GET
#  12, 1, 0.0,        # url structural
#  2, 0, 0,           # url query: /api/users/123 → depth=3
#  0, 0, 0, 0, 0,     # url text: no indicators
#  0, 0.0, 0, 0.0,    # body: empty
#  0, 0, 0, 0, 0]     # body text: all 0
```

---

### How to use this in practice

If you need to extract features from real HTTP requests (proxy logs, captured traffic, etc.):

```python
# Example with an Nginx log
log_line = '127.0.0.1 - - [13/Apr/2026:10:00:00 +0000] ' \
            '"POST /dvwa/vulnerabilities/sqli/?id=%27 HTTP/1.1" 200 1234'

# Parse method and URL from log (format: "METHOD /path?query HTTP/1.1")
parts = log_line.split('"')[1].split()
method = parts[0]
url    = parts[1]

# Call extract_features
features = extract_features(method, url, body=None)
```

For POST requests with an actual body, the body is obtained from the HTTP payload.

---

## Features — complete reference

### Binary (0 or 1)

| Feature | Description |
|---|---|
| `method_is_get` | GET Request |
| `method_is_post` | POST Request |
| `method_is_put` | PUT Request — 100% attacks in CSIC 2010 |
| `url_has_query` | URL has query string (`?`) |
| `url_has_pct27` | `%27` in URL (`'` encoding) |
| `url_has_pct3c` | `%3C` in URL (`<` encoding) |
| `url_has_dashdash` | `--` in URL |
| `url_has_script` | `script` in URL |
| `url_has_select` | `select` in URL |
| `content_has_pct27` | `%27` in body |
| `content_has_pct3c` | `%3C` in body |
| `content_has_dashdash` | `--` in body |
| `content_has_script` | `script` in body |
| `content_has_select` | `select` in body |

### Continuous (numeric values)

| Feature | Type | Description |
|---|---|---|
| `url_length` | int | Total URL length |
| `url_param_count` | int | Number of parameters in query string |
| `url_pct_density` | float | `%` density in URL |
| `url_path_depth` | int | Path depth (`/` segments) |
| `url_query_length` | int | Query string length |
| `content_length` | int | Body length (0 for GET) |
| `content_pct_density` | float | `%` density in body |
| `content_param_count` | int | Number of `=` in body |
| `content_param_density` | float | `content_param_count / content_length` |

---

## Preprocessing in the API

The model was trained with **StandardScaler** applied to 3 continuous features. The API applies the same transformation with hardcoded parameters (fit on the original train set):

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

Binary features are not transformed.

---

## Model and threshold

### Model

- **Algorithm:** LightGBM
- **Dataset:** CSIC 2010 (61,065 requests, 41% attacks)
- **Features:** 23 (v4)
- **n_estimators:** 200
- **Artifact saved with:** `mlflow.sklearn.log_model()`
- **Location:** MLflow server → experiment `mlsec-model-a` → latest run → artifact `model/`

### Threshold

The decision threshold is **0.2903** — not 0.5.

This value was calibrated in the DAG's `train` task to maximize Precision while maintaining Recall ≥ 0.955 on the validation set. The result of that calibration is that:

- **Any probability ≥ 0.2903 → attack (1)**
- **Any probability < 0.2903 → normal (0)**

### About absolute probabilities

!!! warning "Probabilities skewed by scale_pos_weight"
    The model was trained with `scale_pos_weight = neg/pos ≈ 1.44` (the dataset has 59% normal / 41% attacks). This skews the probabilities towards the minority class (attack) and makes the absolute probabilities hard to interpret.

    A normal request might return `probability=0.98` not because the model is sure it's an attack, but because the `scale_pos_weight` artificially inflated the positive class's probability.

    The 0.2903 threshold partially compensates for this — it was specifically calibrated for the target recall level. It is not equivalent to threshold=0.5 of a model without reweighting.

**In practice:** interpret the `prediction` (0/1) as the final decision, and the `probability` as an indicator of relative confidence within the model. Do not use the absolute probability directly as a score.

---

## Model Loading

```
1. Checks MODEL_PATH (env var) → local pickle file
2. If it does not exist → uses MLFLOW_TRACKING_URI → connects to MLflow server
3. Searches for the run with the best test_recall in the mlsec-model-a experiment
4. Downloads model/ artifact from artifact_uri
5. Loads model.pkl into memory
```

If nothing is available → `degraded` mode (`/health` responds 503, `/predict` responds 500).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | MLflow server to download the model |
| `MODEL_PATH` | `models/model_a_lightgbm.pkl` | Local path to the model pickle |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `5082` | Server port |

---

## File structure

```
src/mlsec/api/
├── __init__.py
├── main.py              ← FastAPI app (endpoints)
├── models.py           ← Pydantic schemas (PredictRequest, PredictResponse)
├── model_loader.py     ← Model loading from pickle or MLflow
└── preprocessing.py    ← StandardScaler with hardcoded parameters

docker/
├── Dockerfile.api      ← python:3.11-slim + libgomp1 + deps image
├── docker-compose.yml  ← api service on port 5082
└── ...                 ← MLflow, Airflow, Postgres

requirements-api.txt    ← fastapi, uvicorn, pydantic, lightgbm, mlflow, etc.
```

---

## Known errors

### `scale_pos_weight` inflates probabilities

A normal request can return a 0.98 probability. This is expected — the model was trained to maximize recall, not to calibrate absolute probabilities. Use `prediction` for the binary decision.

### `model_loaded: false` in /health

Check the container logs:
```bash
docker logs pmtmlsec-api-1
```
Common causes:
- `libgomp.so.1` not installed → rebuild with `docker compose build api`
- MLflow not accessible from API → verify `MLFLOW_TRACKING_URI`
- Model run not found → verify the DAG ran at least once
```
