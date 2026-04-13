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

## Estado actual

!!! success "Phase 3 — Training + MLflow — Modelo A concluido"
    **Modelo A (CSIC 2010)** concluido tras 7 iteraciones de feature engineering.
    LightGBM: Recall 0.953 ✅ / Precision 0.793 / ROC-AUC 0.968 — 936 FP.
    Precision ~0.793 aceptada como techo práctico del enfoque actual.

!!! info "Siguiente paso — Modelo B (UNSW-NB15)"
    EDA completo. Preprocessing y training en progreso.
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
