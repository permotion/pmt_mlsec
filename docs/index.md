# PMT MLSec

Sistema de detección de ataques usando Machine Learning, enfocado en workloads web y de red.

---

## Qué hace

Dos modelos de clasificación binaria para detección offline de ataques:

<div class="grid cards" markdown>

-   :material-web: **Modelo A — Web Attack Detection**

    ---

    Detecta ataques HTTP usando el dataset CSIC 2010.
    Input: features de request HTTP.
    Output: `normal` / `attack`

    [:octicons-arrow-right-24: Ver Modelo A](model_a/index.md)

-   :material-lan: **Modelo B — Network Attack Detection**

    ---

    Detecta ataques de red usando el dataset UNSW-NB15.
    Input: features de flujo de red.
    Output: `benign` / `malicious`

    [:octicons-arrow-right-24: Ver Modelo B](model_b/index.md)

</div>

---

## Prueba de concepto — Evaluación de requests reales

Esta es la demostración más directa del Modelo A funcionando en la práctica. Se toma un request HTTP en formato de log de Nginx y se evalúa contra el modelo:

### Script: `eval_log_line.py`

```
scripts/eval_log_line.py
```

Parsea líneas de log en Combined Log Format (estándar de Nginx/Apache), extrae method y URL, computa las 23 features, y devuelve la predicción del modelo.

```bash
# Evaluar un log individual
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py '<log_line>'

# Modo interactivo
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py --interactive
```

### Caso — GET con SQL injection en query string

```
192.168.1.100 - - [14/Apr/2026:10:23:45 -0300] "GET /login?username=admin%27%20OR%201%3D1%20--&password=test HTTP/1.1" 200 1234 "-" "Mozilla/5.0"
```

**Resultado:** 🔴 **ATAQUE** — Probabilidad: 100.0%

El modelo detecta correctamente el ataque. La URL contiene `%27%20OR%201%3D1%20--` (decodificado: `' OR 1=1 --`), un SQL injection clássico. Las features que activan la detección:

| Feature | Valor | Qué indica |
|---|---|---|
| `url_pct_density` | 0.151 | Alta densidad de `%` (8% de la URL) — encoding atípico en tráfico normal |
| `url_has_pct27` | 1 | `%27` (comilla simple codificada) — señal directa de SQLi |
| `url_has_dashdash` | 1 | `--` (comentario SQL) — técnica común para truncar queries |

### Limitación

Los logs de access de Nginx/Apache **no contienen el body de los requests POST**. El ataque podría estar oculto en el body y no sería visible en el log. Para capturar bodies se necesita un WAF, proxy, o IDS que registre los payloads completos.

Ver el análisis completo en [Model A — Análisis post-training](model_a_analysis.md).

Ver el análisis completo en [Model A — Análisis post-training](model_a_analysis.md).

---

## Estado actual

!!! warning "Phase 3 — Modelo A training ✅ | Phase 4 — Airflow + Docker ✅ | Phase 5 — API ✅"
    **Modelo A (CSIC 2010):** 7 iteraciones de feature engineering.
    LightGBM: Recall 0.954 ✅ / Precision 0.793 ❌ (target 0.85) / ROC-AUC 0.968.
    **API de inferencia** funcionando en puerto 5082: `/health`, `/features`, `/predict`.
    **Docker Compose** con MLflow + Airflow + Postgres + API.
    Análisis post-training completo: [Model A — Análisis post-training](model_a_analysis.md).

!!! info "Siguiente paso — Modelo B (UNSW-NB15)"
    EDA completo. Preprocessing pendiente.
    Ver el [roadmap completo](roadmap.md) y el [brief del proyecto](brief.md).

---

## Stack

| Herramienta | Rol |
|---|---|
| Python 3.11 | Lenguaje principal |
| scikit-learn | Modelos ML |
| MLflow | Experiment tracking |
| Apache Airflow | Orquestación (Phase 2+) |
| Jupyter | EDA y exploración |

---

## Levantar la documentación localmente

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Abre [http://localhost:8000](http://localhost:8000) en el browser.
