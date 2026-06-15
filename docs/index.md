# PMT MLSec

Attack detection system using Machine Learning, focused on web and network workloads.

---

## What it does

Two binary classification models for offline attack detection:

<div class="grid cards" markdown>

-   :material-web: **Model A — Web Attack Detection**

    ---

    Detects HTTP attacks using the CSIC 2010 dataset.
    Input: HTTP request features.
    Output: `normal` / `attack`

    [:octicons-arrow-right-24: View Model A](model_a/index.md)

-   :material-lan: **Model B — Network Attack Detection**

    ---

    Detects network attacks using the UNSW-NB15 dataset.
    Input: network flow features.
    Output: `benign` / `malicious`

    [:octicons-arrow-right-24: View Model B](model_b/index.md)

</div>

---

## Proof of Concept — Evaluating real requests

This is the most direct demonstration of Model A working in practice. An HTTP request in Nginx log format is taken and evaluated against the model:

### Script: `eval_log_line.py`

```
scripts/eval_log_line.py
```

Parses log lines in Combined Log Format (Nginx/Apache standard), extracts method and URL, computes the 23 features, and returns the model prediction.

```bash
# Evaluate a single log
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py '<log_line>'

# Interactive mode
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py --interactive
```

### Case — GET with SQL injection in query string

```
192.168.1.100 - - [14/Apr/2026:10:23:45 -0300] "GET /login?username=admin%27%20OR%201%3D1%20--&password=test HTTP/1.1" 200 1234 "-" "Mozilla/5.0"
```

**Result:** 🔴 **ATTACK** — Probability: 100.0%

The model correctly detects the attack. The URL contains `%27%20OR%201%3D1%20--` (decoded: `' OR 1=1 --`), a classic SQL injection. The features that trigger detection:

| Feature | Value | What it indicates |
|---|---|---|
| `url_pct_density` | 0.151 | High density of `%` (8% of the URL) — atypical encoding in normal traffic |
| `url_has_pct27` | 1 | `%27` (encoded single quote) — direct signal of SQLi |
| `url_has_dashdash` | 1 | `--` (SQL comment) — common technique to truncate queries |

### Limitation

Nginx/Apache access logs **do not contain the POST request body**. The attack could be hidden in the body and would not be visible in the log. To capture bodies, a WAF, proxy, or IDS is needed to record the full payloads.

See the full analysis in [Model A — Post-training analysis](model_a_analysis.md).

---

## Current status

!!! warning "Phase 3 — Model A training ✅ | Phase 4 — Airflow + Docker ✅ | Phase 5 — API ✅"
    **Model A (CSIC 2010):** 7 iterations of feature engineering.
    LightGBM: Recall 0.954 ✅ / Precision 0.793 ❌ (target 0.85) / ROC-AUC 0.968.
    **Inference API** running on port 5082: `/health`, `/features`, `/predict`.
    **Docker Compose** with MLflow + Airflow + Postgres + API.
    Complete post-training analysis: [Model A — Post-training analysis](model_a_analysis.md).

!!! info "Next step — Model B (UNSW-NB15)"
    EDA and preprocessing complete. Training pending.
    See the [full roadmap](roadmap.md) and the [project brief](brief.md).

---

## Stack

| Tool | Role |
|---|---|
| Python 3.11 | Main language |
| scikit-learn | ML models |
| MLflow | Experiment tracking |
| Apache Airflow | Orchestration (Phase 2+) |
| Jupyter | EDA and exploration |

---

## Serve documentation locally

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Open [http://localhost:8000](http://localhost:8000) in the browser.
