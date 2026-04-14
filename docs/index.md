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

Esta es la demostración más directa del Modelo A funcionando en la práctica. Se toman requests HTTP en formato de log de Nginx y se evalúan contra el modelo:

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

### Caso 1 — GET con SQL injection ✅ Detectado

```
192.168.1.100 - - [14/Apr/2026:10:23:45 -0300] "GET /login?username=admin%27%20OR%201%3D1%20--&password=test HTTP/1.1" 200 1234 "-" "Mozilla/5.0"
```

**Resultado:** 🔴 **ATAQUE** — Probabilidad: 100.0%

El modelo detecta correctamente el ataque. La URL contiene `%27%20OR%201%3D1%20--` (decodificado: `' OR 1=1 --`), un SQL injection clásico. Las features que activan la detección:

| Feature | Valor | Qué indica |
|---|---|---|
| `url_pct_density` | 0.151 | Alta densidad de `%` (8% de la URL) — encoding atypical en tráfico normal |
| `url_has_pct27` | 1 | `%27` (comilla simple codificada) — señal directa de SQLi |
| `url_has_dashdash` | 1 | `--` (comentario SQL) — técnica común para truncate queries |

### Caso 2 — POST login normal ❌ Falso positivo

```
192.168.1.100 - - [14/Apr/2026:10:26:01 -0300] "POST /api/login HTTP/1.1" 200 456 "-" "Mozilla/5.0"
```

**Resultado:** 🔴 **ATAQUE** — Probabilidad: 99.9%

Este es un **falso positivo**. El request es perfectamente legítimo — un POST a `/api/login`. El modelo devuelve 99.9% de probabilidad de ataque por el efecto de `scale_pos_weight=1.44` usado en training, que distorsiona las probabilidades hacia la clase positiva.

### Conclusión de la prueba

El modelo detecta ataques reales con alta probabilidad (100%) pero también marca requests legítimos con probabilidad igualmente alta (99.9%). **No existe una zona de incertidumbre** — el modelo asigna probabilidades extremas tanto a ataques como a normales.

**Implicación para producción:** el modelo sirve como herramienta de triaje para revisión manual, no como decisor automático de bloqueo sin una segunda capa de validación.

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
