# Airflow — Setup y DAGs

Apache Airflow orquesta el pipeline de training: encadena preprocessing → training → evaluación y garantiza que cada paso se ejecute en orden, con logs y estado visible en la UI.

Hay dos formas de correrlo: **local** (desarrollo, tiene limitaciones en macOS ARM) y **Docker** (producción, recomendado).

---

## Docker — Setup de producción

### Estructura

```
docker/
├── Dockerfile.airflow        # apache/airflow:2.10.4 + libgomp1 + deps ML
├── Dockerfile.mlflow        # python:3.11-slim + mlflow 2.22.4
├── docker-compose.yml       # todos los servicios
├── init-dbs.sql            # crea DB mlflow en postgres
└── migrate_mlflow.py       # migración runs SQLite → Postgres
```

### Servicios

| Servicio | Puerto | Descripción |
|---|---|---|
| `postgres` | 5432 | Backend store compartido (Airflow + MLflow) |
| `mlflow` | 5081 | Tracking server MLflow 2.22.4 |
| `airflow-webserver` | 5080 | UI de Airflow (admin / admin) |
| `airflow-scheduler` | — | Ejecuta los DAGs |

### Cómo levantar

```bash
# Arrancar todo
cd docker && docker compose up

# Parar (preserva datos en volúmenes)
docker compose -f docker/docker-compose.yml down

# Limpiar todo incluyendo volúmenes
docker compose -f docker/docker-compose.yml down -v
```

UI: `http://localhost:5080` (admin / admin)  
MLflow: `http://localhost:5081`

### Migración de runs MLflow

Si hay runs en `mlflow.db` (SQLite local) y se quiere pasarlos al servidor Docker:

```bash
.venv/bin/python docker/migrate_mlflow.py
```

Esto migra: params, métricas, tags, run name, status. Los artefactos de modelo no se migran.

### Rebuild después de cambios

Si se modifica `requirements-ml.txt` o un Dockerfile:

```bash
docker compose -f docker/docker-compose.yml build [servicio]
docker compose -f docker/docker-compose.yml up -d --force-recreate [servicio]
```

---

## Local — Setup de desarrollo

### Requisitos

Airflow tiene un árbol de dependencias grande que puede chocar con scikit-learn y LightGBM. Se instala en un entorno separado:

```bash
python3.12 -m venv .venv-airflow
AIRFLOW_VERSION=2.10.4
PYTHON_VERSION=3.12
.venv-airflow/bin/pip install "apache-airflow==${AIRFLOW_VERSION}" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
```

!!! note "Python 3.12 requerido"
    Airflow 2.10.4 no soporta Python 3.13 (versión del `.venv` principal).
    El entorno `.venv-airflow` usa Python 3.12 exclusivamente para Airflow.
    Los scripts de ML siguen corriendo con `.venv` (Python 3.13).

### Cómo levantar

Se necesitan **dos terminales**:

**Terminal 1 — webserver:**
```bash
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow webserver --port 5080 --debug
```

**Terminal 2 — scheduler:**
```bash
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow scheduler 2>&1 | grep -v "SIGSEGV\|Worker (pid"
```

UI: `http://localhost:5080` (admin / admin)

!!! warning "SIGSEGV en macOS ARM"
    En macOS Apple Silicon, el scheduler levanta un servidor de logs interno (puerto 8793) que crashea con `fork()`. No afecta la ejecución de los DAGs. Para desarrollo local usar Docker (ver arriba) si los DAGs no corren.

### Configuración aplicada

En `airflow/airflow.cfg`:

| Parámetro | Valor | Razón |
|---|---|---|
| `dags_folder` | `<root>/dags/` | Apunta a la carpeta del proyecto |
| `load_examples` | `False` | Evita cargar los DAGs de ejemplo |
| `workers` | `1` | macOS ARM — evita crashes de gunicorn |
| `worker_class` | `gthread` | macOS ARM — evita crashes de gunicorn |

---

## DAG — dag_model_a

**Archivo:** `dags/dag_model_a.py`
**Trigger:** manual (`schedule=None`)
**Tags:** `model-a`, `csic2010`

### Pipeline

```
verify_data → preprocess → train → evaluate
```

| Tarea | Tipo | Qué hace |
|---|---|---|
| `verify_data` | PythonOperator | Verifica que `csic_database.csv` existe |
| `preprocess` | BashOperator | Corre `preprocess_csic_v4.py` → genera `features_v4.parquet` |
| `train` | BashOperator | Corre `train_model_a_pipeline.py` con MLflow logging |
| `evaluate` | BashOperator | Verifica shape del parquet generado |

### Cómo triggerear

1. Entrá a `http://localhost:5080`
2. Buscá `dag_model_a`
3. Activá el toggle (arranca pausado)
4. Click en **▶ Trigger DAG**
5. Monitoreá en Graph o Grid

### Interpreter

En Docker usa `python3` (MLSEC_PYTHON configurado en `docker-compose.yml`). En local usa `.venv/bin/python`.

### Exit codes

`train_model_a_pipeline.py` usa exit codes para comunicar el resultado a Airflow:

| Exit code | Significado |
|---|---|
| `0` | Recall ≥ 0.95 en test — pipeline exitoso |
| `1` | Recall < 0.95 — tarea marcada como fallida |

### Resultados en MLflow

Cada ejecución del DAG loggea un run en el experimento `mlsec-model-a` con nombre `model-a-lightgbm-pipeline`.

En Docker: `http://localhost:5081` → experimento `mlsec-model-a`  
En local: `mlflow ui --backend-store-uri sqlite:///mlflow.db`

---

## Estructura de archivos

```
docker/
├── Dockerfile.airflow        # imagen con ML deps + libgomp1
├── Dockerfile.mlflow        # python:3.11-slim + mlflow 2.22.4
├── docker-compose.yml       # servicios
├── init-dbs.sql            # DB mlflow en postgres
└── migrate_mlflow.py       # migración runs

dags/
└── dag_model_a.py          ← DAG de Airflow

src/mlsec/models/
└── train_model_a_pipeline.py   ← Script de training para el DAG

airflow/                    ← Runtime local (no versionado)
├── airflow.cfg
├── airflow.db
└── logs/

mlflow.db                   ← SQLite local (no versionado)
```
