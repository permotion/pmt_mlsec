# CLAUDE.md — PMT MLSec

Leé este archivo completo antes de hacer cualquier cambio al proyecto.

---

## Qué es este proyecto

**PMT MLSec** es un sistema de detección de ataques usando Machine Learning.
MVP con dos modelos de clasificación binaria:

| Modelo | Input | Dataset | Output |
|---|---|---|---|
| A — Web Attack Detection | Request HTTP features | CSIC 2010 | normal / attack |
| B — Network Attack Detection | Features de flujo de red | UNSW-NB15 | benign / malicious |

Detección **offline** en el MVP — no hay bloqueo en tiempo real todavía.

---

## Fase actual

**Phase 1 — Definición + Ingesta de datasets**

- Criterios de éxito del MVP definidos
- Datasets a descargar: CSIC 2010, UNSW-NB15
- El training pipeline todavía no existe

Ver `docs/roadmap.md` para el detalle completo de fases.

---

## Tech stack

| Herramienta | Rol |
|---|---|
| Python 3.11 | Lenguaje principal |
| Jupyter Notebooks | EDA y exploración |
| scikit-learn | Modelos ML |
| pandas / numpy | Procesamiento de datos |
| MLflow | Experiment tracking, model registry |
| Apache Airflow | Orquestación de pipelines |
| MkDocs + Material | Documentación en browser |

Storage: **local** en `data/` durante el MVP. Sin DVC por ahora.

---

## Estructura del repo

```
PMT MLSec/
├── CLAUDE.md                  ← estás aquí
├── mkdocs.yml                 ← config de documentación
├── requirements.txt           ← dependencias Python del proyecto
├── requirements-docs.txt      ← dependencias de MkDocs
├── .claude/
│   ├── settings.json
│   └── commands/              ← slash commands custom
│       ├── eda.md             → /eda
│       ├── train.md           → /train
│       ├── eval.md            → /eval
│       ├── ingest.md          → /ingest
│       ├── dag.md             → /dag
│       ├── experiment-summary.md → /experiment-summary
│       └── refactor-notebook.md  → /refactor-notebook
├── docs/                      ← documentación del proyecto (MkDocs)
│   ├── index.md
│   ├── roadmap.md
│   ├── datasets.md
│   ├── models.md
│   ├── experiments.md
│   └── mlflow.md
├── data/
│   ├── raw/
│   │   ├── csic2010/          ← dataset original sin tocar
│   │   └── unsw_nb15/         ← dataset original sin tocar
│   └── processed/
│       ├── csic2010/          ← features listas para training
│       └── unsw_nb15/
├── notebooks/
│   ├── eda/                   ← exploración de datos
│   └── experiments/           ← prototipado de modelos
├── src/
│   └── mlsec/
│       ├── data/              ← loaders, preprocessing
│       ├── features/          ← feature engineering
│       └── models/            ← definición de modelos, training
├── models/                    ← artefactos de modelos entrenados
└── dags/                      ← DAGs de Airflow
```

---

## Convenciones

### Datasets en `data/raw/`
- Nunca modificar archivos en `data/raw/` — son la fuente de verdad
- Cada dataset tiene su subcarpeta con `README.md`, `LICENSE`, y hash SHA-256
- El procesamiento siempre lee de `raw/` y escribe en `processed/`

### Labels
- `0` = benign / normal
- `1` = malicious / attack
- Consistente en ambos modelos

### Métricas objetivo MVP

| Modelo | Recall mínimo | Precision mínima | F1 mínimo | ROC-AUC mínimo |
|---|---|---|---|---|
| A — CSIC 2010 | 0.95 | 0.85 | — | — |
| B — UNSW-NB15 | — | — | 0.88 | 0.95 |

### Notebooks
- Usados **solo** para EDA y exploración
- Nunca llamar notebooks desde Airflow DAGs
- Cuando un notebook madura → `/refactor-notebook` lo convierte en script

### MLflow
- Cada experimento: un run con parámetros loggeados, métricas, y artefactos
- Naming: `mlsec-model-a-{descripcion}` / `mlsec-model-b-{descripcion}`
- Ver `docs/mlflow.md` para convenciones de naming completas

### Airflow DAGs
- Un DAG por modelo: `dag_model_a.py`, `dag_model_b.py`
- Tareas mínimas: `ingest → preprocess → train → evaluate → register`
- Ver `docs/roadmap.md` para cuándo introducir Airflow

---

## Qué NO tocar

- `data/raw/` — nunca modificar datos crudos
- `mlruns/` — generado por MLflow, no editar a mano
- Airflow en Phase 1 — todavía no existe, se introduce en Phase 2

---

## Documentación

```bash
# Levantar docs en el browser
pip install -r requirements-docs.txt
mkdocs serve   # → http://localhost:8000
```

---

## Cómo trabajar con Claude Code

Antes de implementar algo:
1. Revisá `docs/roadmap.md` para confirmar que estamos en la fase correcta
2. Revisá `docs/datasets.md` para el formato y fuente del dataset
3. Revisá `docs/models.md` para las decisiones de arquitectura tomadas
4. Seguí las convenciones de naming y labels definidas arriba
5. Si el trabajo es en notebook → script, usá `/refactor-notebook`

Ante la duda, preguntá antes de implementar.
