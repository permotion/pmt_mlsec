#!/usr/bin/env python3
"""
Evalúa un string de log de Nginx/Apache Combined Log Format.

Uso:
    python eval_log_line.py '<log_line>'
    python eval_log_line.py --interactive

Ejemplo de log:
    192.168.1.100 - - [14/Apr/2026:10:23:45 -0300] "GET /login?username=admin%27%20OR%201%3D1%20--&password=test HTTP/1.1" 200 1234 "-" "Mozilla/5.0"
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
import requests
import tempfile
import pickle
import mlflow

# ---------------------------------------------------------------------------
# Parser de Combined Log Format (Nginx/Apache)
# ---------------------------------------------------------------------------
# Formato:
# $remote_addr - - [$time_local] "$method $uri $protocol" $status $body_bytes_sent "$referer" "$user_agent"
LOG_PATTERN = re.compile(
    r'^[\d\.]+\s+\S+\s+\S+\s+\[([^\]]+)\]\s+'
    r'"(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH)\s+(\S+?)(?:\?([^"]*))?\s+HTTP/[^"]+"\s+'
    r'\d+\s+\d+\s+"[^"]*"\s+"[^"]*"'
)


def parse_log_line(line: str) -> dict | None:
    """
    Parsea una línea de log en Combined Log Format.

    Args:
        line: línea de log cruda

    Returns:
        dict con keys: method, url, query_string, body (vacío para GET)
        None si no matchea el patrón
    """
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None

    time_local, method, uri, query_string = match.groups()

    # Reconstruir URL completa
    url = uri
    if query_string:
        url = f"{uri}?{query_string}"

    # En logs de access, no hay body visible — se infiere vacío
    # (el body real está en el request POST, no en el log de access)
    body = ""

    return {
        "method": method.upper(),
        "url": url,
        "body": body,
        "raw": line.strip(),
    }


# ---------------------------------------------------------------------------
# Feature extraction (copiado de preprocess_csic_v4.py para ser self-contained)
# ---------------------------------------------------------------------------
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
    """
    m = method.upper()
    method_is_get  = 1 if m == "GET"  else 0
    method_is_post = 1 if m == "POST" else 0
    method_is_put  = 1 if m == "PUT"  else 0

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
        method_is_get, method_is_post, method_is_put,
        url_length, url_param_count, url_pct_density,
        url_path_depth, url_query_length, url_has_query,
        url_has_pct27, url_has_pct3c, url_has_dashdash,
        url_has_script, url_has_select,
        content_length, content_pct_density,
        content_param_count, content_param_density,
        content_has_pct27, content_has_pct3c, content_has_dashdash,
        content_has_script, content_has_select,
    ]


# ---------------------------------------------------------------------------
# Cargar modelo desde MLflow (mismo approach que los scripts de análisis)
# ---------------------------------------------------------------------------
def load_model():
    tracking_uri = "http://localhost:5081"
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.tracking.MlflowClient()

    exp = client.get_experiment_by_name("mlsec-model-a")
    runs = client.search_runs(
        experiment_ids=[exp.experiment_id],
        filter_string="attributes.status = 'FINISHED'",
        order_by=["metrics.test_recall DESC"],
    )
    run_id = runs[0].info.run_id

    artifact_root = "file:///opt/mlflow/artifacts"
    model_url = f"http://localhost:5083/1/{run_id}/artifacts/model/model.pkl"

    response = requests.get(model_url, stream=True)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        f.write(response.content)
        model_path = f.name

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    return model


def evaluate_log_line(line: str, model=None) -> dict:
    """
    Evalúa una línea de log y devuelve el resultado del modelo.
    """
    parsed = parse_log_line(line)
    if parsed is None:
        return {"error": "No se pudo parsear la línea de log", "raw": line}

    method = parsed["method"]
    url    = parsed["url"]
    body   = parsed["body"]

    features = extract_features(method, url, body)
    feature_names = [
        "method_is_get", "method_is_post", "method_is_put",
        "url_length", "url_param_count", "url_pct_density",
        "url_path_depth", "url_query_length", "url_has_query",
        "url_has_pct27", "url_has_pct3c", "url_has_dashdash",
        "url_has_script", "url_has_select",
        "content_length", "content_pct_density", "content_param_count",
        "content_param_density",
        "content_has_pct27", "content_has_pct3c", "content_has_dashdash",
        "content_has_script", "content_has_select",
    ]

    if model is None:
        model = load_model()

    X = pd.DataFrame([features], columns=feature_names)
    proba = float(model.predict_proba(X)[:, 1][0])
    threshold = 0.2903
    prediction = "ATAQUE" if proba >= threshold else "NORMAL"
    proba_pct = proba * 100

    return {
        "prediction": prediction,
        "probability": round(proba_pct, 1),
        "threshold_pct": round(threshold * 100, 1),
        "method": method,
        "url": url,
        "body": body or "(vacío — GET)",
        "features": dict(zip(feature_names, features)),
    }


def pretty_print(result: dict):
    if "error" in result:
        print(f"❌ Error: {result['error']}")
        print(f"   Raw: {result['raw']}")
        return

    emoji = "🔴" if result["prediction"] == "ATAQUE" else "🟢"
    print(f"{emoji} {result['prediction']}")
    print(f"   Probabilidad: {result['probability']}% (threshold: {result['threshold_pct']}%)")
    print(f"   Method: {result['method']}")
    print(f"   URL: {result['url']}")
    print(f"   Body: {result['body']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--interactive":
        print("Evaludor de logs — escribí una línea de log y presioná Enter (Ctrl+C para salir)\n")
        model = load_model()
        while True:
            try:
                line = input("log> ")
                if line.strip():
                    result = evaluate_log_line(line, model=model)
                    pretty_print(result)
                    print()
            except (KeyboardInterrupt, EOFError):
                break
    else:
        log_line = " ".join(sys.argv[1:])
        result = evaluate_log_line(log_line)
        pretty_print(result)
