"""
DAG — Batch Inference (access log → ataque detection)

Proceso:
    check_log_exists → process_log → send_alert

El archivo access0.log debe estar en:
    /opt/airflow/data/uploads/access0.log

Trigger: manual (schedule=None)

Uso:
    1. Colocar access0.log en /opt/airflow/data/uploads/
    2. Triggerear el DAG desde Airflow UI
    3. Ver resultados en los logs de las tasks
"""

import re
from datetime import datetime
from pathlib import Path

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
LOG_FILE = Path("/opt/airflow/data/uploads/access0.log")
API_URL = "http://api:5000/predict"  # hostname 'api' como está definido en docker-compose
THRESHOLD_ATTACK_COUNT = 2  # si hay más de 2 ataques, se considera alerta

# ---------------------------------------------------------------------------
# Parser — Combined Log Format (Apache/Nginx)
# ---------------------------------------------------------------------------
LOG_PATTERN = re.compile(
    r"^[\d\.]+\s+\S+\s+\S+\s+\[([^\]]+)\]\s+"
    r'"(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH)\s+(\S+?)(?:\?([^"]*))?\s+HTTP/[^"]+"\s+'
    r"\d+\s+\d+\s+\"[^\"]*\"\s+\"[^\"]*\""
)


def parse_log_line(line: str) -> dict | None:
    """
    Parsea una línea de log en Combined Log Format.

    Returns:
        dict con keys: method, url, body (vacío para GET)
        None si no matchea el patrón
    """
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None

    time_local, method, uri, query_string = match.groups()

    url = uri
    if query_string:
        url = f"{uri}?{query_string}"

    # Los access logs no tienen body visible — se trata como vacío
    body = ""

    return {
        "method": method.upper(),
        "url": url,
        "body": body,
    }


# ---------------------------------------------------------------------------
# Feature extraction — mismo proceso que preprocess_csic_v4.py
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

    Args:
        method: método HTTP (GET, POST, PUT, etc.)
        url:    URL completa (con o sin scheme)
        body:   body del request (None o "" para GET)

    Returns:
        Lista ordenada de 23 floats — el orden es el de FEATURE_NAMES.
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


FEATURE_NAMES = [
    "method_is_get", "method_is_post", "method_is_put",
    "url_length", "url_param_count", "url_pct_density",
    "url_path_depth", "url_query_length", "url_has_query",
    "url_has_pct27", "url_has_pct3c", "url_has_dashdash",
    "url_has_script", "url_has_select",
    "content_length", "content_pct_density",
    "content_param_count", "content_param_density",
    "content_has_pct27", "content_has_pct3c", "content_has_dashdash",
    "content_has_script", "content_has_select",
]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
def check_log_exists():
    """Verifica que el archivo de log exista en la ruta esperada."""
    if not LOG_FILE.exists():
        raise FileNotFoundError(
            f"Log file no encontrado: {LOG_FILE}\n"
            f"Colocar access0.log en /opt/airflow/data/uploads/"
        )
    size_kb = LOG_FILE.stat().st_size / 1024
    print(f"Log file encontrado: {LOG_FILE} ({size_kb:.1f} KB)")


def process_log(templates_dict: dict):
    """
    Lee el log, extrae features de cada línea, llama a la API,
    y devuelve el resumen de detecciones.
    """
    with open(LOG_FILE, "r") as f:
        lines = f.readlines()

    total_lines = len(lines)
    processed = 0
    attacks = 0
    errors = 0
    attack_details = []

    for i, line in enumerate(lines):
        parsed = parse_log_line(line)
        if parsed is None:
            # Línea que no matchea el formato — se ignora
            continue

        method = parsed["method"]
        url    = parsed["url"]
        body   = parsed["body"]

        features = extract_features(method, url, body)

        # Armar payload para la API
        payload = dict(zip(FEATURE_NAMES, features))

        try:
            response = requests.post(
                API_URL,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("prediction") == 1:
                attacks += 1
                attack_details.append({
                    "line_number": i + 1,
                    "method": method,
                    "url": url,
                    "probability": result.get("probability", 0),
                })

            processed += 1

        except requests.RequestException as exc:
            errors += 1
            print(f"Error en línea {i + 1}: {exc}")
            continue

    # Guardar resultados en XCom para la siguiente task
    summary = {
        "total_lines": total_lines,
        "processed": processed,
        "attacks": attacks,
        "errors": errors,
        "attack_details": attack_details,
        "timestamp": datetime.now().isoformat(),
    }

    print(f"\n{'='*60}")
    print(f"BATCH INFERENCE — RESUMEN")
    print(f"{'='*60}")
    print(f"Total líneas en log:      {total_lines}")
    print(f"Líneas procesadas:       {processed}")
    print(f"Ataques detectados:       {attacks}")
    print(f"Errores:                  {errors}")
    print(f"Timestamp:               {summary['timestamp']}")
    print(f"{'='*60}\n")

    return summary


def send_alert(templates_dict: dict, ti=None):
    """
    Imprime el mensaje de alerta con los resultados.
    Si hay más de THRESHOLD_ATTACK_COUNT ataques, imprime advertencia.
    """
    summary = ti.xcom_pull(task_ids="process_log")

    if summary is None:
        print("No se recibieron resultados de process_log")
        return

    attacks = summary["attacks"]
    attack_details = summary.get("attack_details", [])

    print(f"\n{'='*60}")
    print(f"ALERTA — DETECCIÓN DE ATAQUES")
    print(f"{'='*60}")
    print(f"Fecha:     {summary['timestamp']}")
    print(f"Log file:  {LOG_FILE}")
    print(f"Ataques detectados: {attacks}")

    if attacks > THRESHOLD_ATTACK_COUNT:
        print(f"\n⚠️  ALERTA: Se detectaron {attacks} ataques (umbral: {THRESHOLD_ATTACK_COUNT})")
    elif attacks > 0:
        print(f"\n✅ Se detectaron {attacks} ataque(s) — bajo umbral de alerta ({THRESHOLD_ATTACK_COUNT})")
    else:
        print(f"\n✅ No se detectaron ataques")

    if attack_details:
        print(f"\nDetalle de ataques detectados:")
        for a in attack_details[:20]:  # mostrar max 20
            print(f"  - Línea {a['line_number']}: {a['method']} {a['url'][:80]} (prob: {a['probability']:.4f})")
        if len(attack_details) > 20:
            print(f"  ... y {len(attack_details) - 20} más")

    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------
with DAG(
    dag_id="dag_batch_inference",
    description="Batch inference — detecta ataques en access.log",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["batch", "inference", "security"],
) as dag:

    check_log = PythonOperator(
        task_id="check_log_exists",
        python_callable=check_log_exists,
    )

    process = PythonOperator(
        task_id="process_log",
        python_callable=process_log,
        provide_context=True,
    )

    alert = PythonOperator(
        task_id="send_alert",
        python_callable=send_alert,
        provide_context=True,
    )

    check_log >> process >> alert