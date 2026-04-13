# Airflow — Setup y DAGs

Apache Airflow orquesta el pipeline de training: encadena preprocessing → training → evaluación y garantiza que cada paso se ejecute en orden, con logs y estado visible en la UI.

---

## Setup local

### Entorno virtual

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

### Inicialización

```bash
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow db migrate
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow users create \
    --username admin --firstname Admin --lastname User \
    --role Admin --email admin@mlsec.local --password admin
```

Esto crea la base de datos SQLite en `airflow/airflow.db` y el usuario admin.

### Configuración aplicada

En `airflow/airflow.cfg` se modificaron dos valores respecto al default:

| Parámetro | Valor | Razón |
|---|---|---|
| `dags_folder` | `<root>/dags/` | Apunta a la carpeta del proyecto |
| `load_examples` | `False` | Evita cargar los DAGs de ejemplo |
| `workers` | `1` | macOS ARM — evita crashes de gunicorn |
| `worker_class` | `gthread` | macOS ARM — evita crashes de gunicorn |

---

## Cómo levantar

Se necesitan **dos terminales** abiertas en la raíz del proyecto.

**Terminal 1 — webserver:**
```bash
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow webserver --port 5080 --debug
```

**Terminal 2 — scheduler:**
```bash
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow scheduler 2>&1 | grep -v "SIGSEGV\|Worker (pid"
```

UI disponible en `http://localhost:5080` — usuario `admin`, contraseña `admin`.

!!! warning "SIGSEGV en puerto 8793"
    El scheduler levanta un servidor de logs interno (puerto 8793) que crashea en macOS ARM con gunicorn sync workers. Esto no afecta la ejecución de los DAGs — es ruido de fondo. Los logs de tareas se guardan en `airflow/logs/` y se pueden leer directamente desde ahí si la UI no los muestra.

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
| `verify_data` | PythonOperator | Verifica que `data/raw/csic2010/csic_database.csv` existe |
| `preprocess` | BashOperator | Corre `preprocess_csic_v4.py` con `.venv` → genera `features_v4.parquet` |
| `train` | BashOperator | Corre `train_model_a_pipeline.py` con MLflow logging, `min_recall_val=0.955` |
| `evaluate` | BashOperator | Verifica shape del parquet generado, confirma pipeline completo |

### Cómo triggerear

1. Entrá a `http://localhost:5080`
2. Buscá `dag_model_a` en la lista
3. Activá el toggle (el DAG arranca pausado)
4. Click en **▶ Trigger DAG**
5. Monitoreá el progreso en la vista de Graph o Grid

### Scripts invocados

Los BashOperators corren con el intérprete de `.venv` (no de `.venv-airflow`):

```python
PYTHON = ROOT / ".venv" / "bin" / "python"
```

Airflow actúa como orquestador puro — no necesita scikit-learn ni LightGBM instalados.

### Exit codes

`train_model_a_pipeline.py` usa exit codes para comunicar el resultado a Airflow:

| Exit code | Significado |
|---|---|
| `0` | Recall ≥ 0.95 en test — pipeline exitoso |
| `1` | Recall < 0.95 — tarea marcada como fallida en Airflow |

Si la tarea `train` falla, Airflow la marca en rojo y detiene el pipeline. El run queda loggeado en MLflow independientemente del resultado.

### Resultados en MLflow

Cada ejecución del DAG loggea un run en el experimento `mlsec-model-a` con nombre `model-a-lightgbm-pipeline`:

```bash
mlflow ui --backend-store-uri sqlite:///mlflow.db
# → http://localhost:5000
```

---

## Estructura de archivos

```
dags/
└── dag_model_a.py              ← DAG de Airflow

src/mlsec/models/
└── train_model_a_pipeline.py   ← Script de training para el DAG

airflow/                        ← Runtime de Airflow (no se versiona excepto airflow.cfg)
├── airflow.cfg                 ← Configuración (versionada)
├── airflow.db                  ← SQLite DB (ignorada por git)
└── logs/                       ← Logs de tareas (ignorados por git)
```
