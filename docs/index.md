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

    [:octicons-arrow-right-24: Ver datasets](datasets.md)

-   :material-lan: **Modelo B — Network Attack Detection**

    ---

    Detecta ataques de red usando el dataset UNSW-NB15.
    Input: features de flujo de red.
    Output: `benign` / `malicious`

    [:octicons-arrow-right-24: Ver modelos](models.md)

</div>

---

## Estado actual

!!! info "Phase 1 — Definición + Ingesta de datasets"
    Definiendo criterios de éxito y descargando datasets.
    Ver el [roadmap completo](roadmap.md).

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
