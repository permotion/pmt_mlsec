# Roadmap

## Objetivo del MVP

Construir 2 modelos de detección de ataques con datasets públicos de referencia,
con experiment tracking via MLflow y detección **offline** (sin bloqueo en tiempo real).

---

## Modelos

| Modelo | Input | Dataset | Output |
|---|---|---|---|
| A — Web Attack Detection | Features de request HTTP | CSIC 2010 | normal / attack |
| B — Network Attack Detection | Features de flujo de red | UNSW-NB15 | benign / malicious |

---

## Criterios de éxito

### Labels
- `0` = benign / normal
- `1` = malicious / attack

### Métricas

Las métricas de evaluación son: **Precision**, **Recall**, **F1**, **ROC-AUC**.

### Umbrales mínimos por modelo

| Modelo | Recall mínimo | Precision mínima | F1 mínimo | ROC-AUC mínimo |
|---|---|---|---|---|
| A — CSIC 2010 | **0.95** | **0.85** | — | — |
| B — UNSW-NB15 | — | — | **0.88** | **0.95** |

!!! note "Por qué umbrales distintos"
    En detección de ataques, el costo de un falso negativo (ataque no detectado)
    es mayor que el de un falso positivo. Por eso priorizamos Recall alto.
    El threshold de decisión se define explícitamente — no se asume 0.5.

---

## Fases

### Phase 1 — Definición + Ingesta ✅

**Estado:** completa

**Qué hicimos:**

- Definimos el objetivo del MVP: dos modelos de clasificación binaria (web + red)
- Definimos los criterios de éxito por modelo (Recall ≥ 0.95 para CSIC, F1 ≥ 0.88 / ROC-AUC ≥ 0.95 para UNSW-NB15)
- Descargamos y organizamos los datasets en `data/raw/`
- Verificamos integridad con hashes SHA-256
- Documentamos fuentes, licencias y estructura en `docs/datasets.md`

**Entregables:**

- [x] Objetivo del MVP definido
- [x] Criterios de éxito por modelo definidos
- [x] Dataset CSIC 2010 descargado en `data/raw/csic2010/`
- [x] Dataset UNSW-NB15 descargado en `data/raw/unsw_nb15/`
- [x] Hashes SHA-256 verificados (`CHECKSUMS.sha256` en cada carpeta)
- [x] `docs/datasets.md` actualizado con fuentes y licencias

**Archivos relevantes:**

```
data/raw/csic2010/
├── csic_database.csv          ← dataset original (61.065 requests HTTP)
├── README.md
└── CHECKSUMS.sha256

data/raw/unsw_nb15/
├── UNSW_NB15_training-set.parquet   ← 175.341 flujos de red
├── UNSW_NB15_testing-set.parquet    ← 82.332 flujos de red
├── README.md
└── CHECKSUMS.sha256
```

---

### Phase 2 — EDA + Preprocessing ✅

**Estado:** completo

#### Phase 2.1 — EDA ✅

**Qué hicimos:**

Exploramos los dos datasets en Jupyter Notebooks para entender su estructura, detectar problemas de calidad, decidir qué features construir y definir las estrategias de preprocessing antes de escribir una sola línea de código de producción.

**CSIC 2010** (`notebooks/eda/csic2010_eda.ipynb`):

- Confirmamos que el label ya estaba en 0/1 — sin transformación necesaria
- Identificamos que los ataques viven en la URL (GET) y en el body (POST)
- Descubrimos que PUT = 100% ataques — la feature más poderosa del dataset
- Descubrimos que los atacantes siempre usan URL encoding (`%27`, `%3C`) — nunca chars literales
- Descartamos 11 columnas constantes sin información
- Construimos y evaluamos las features binarias de texto (indicadores de SQLi/XSS)
- Definimos la estrategia de desbalance: `class_weight='balanced'` (desbalance leve 59/41)

**UNSW-NB15** (`notebooks/eda/unsw_nb15_eda.ipynb`):

- Confirmamos label 0/1 en ambos splits (train/test predefinidos en parquet)
- Identificamos desbalance inverso: 68% ataques en train — más ataques que tráfico normal
- Analizamos las 9 categorías de ataque y su distribución (Generic 33%, Exploits 28%, Fuzzers 15%)
- Confirmamos que no hay nulos — el dataset está completo
- Definimos estrategia de encoding por columna: top-10+other para `proto` (133 valores), one-hot directo para `service` y `state`
- Detectamos outliers extremos (`sbytes` max 12M, `sload` max 5.9B) → estrategia: `RobustScaler`
- Calculamos correlaciones con el label: `dload` (-0.394), `rate` (0.338), `ct_dst_sport_ltm` (0.357)
- Identificamos features redundantes con el heatmap: `swin`/`dwin` (0.99), `dpkts`/`dloss` (0.98)
- Descartamos `dwin`, `dloss`, `is_sm_ips_ports` por redundancia

**Entregables:**

- [x] `notebooks/eda/csic2010_eda.ipynb` ✅
- [x] `notebooks/eda/unsw_nb15_eda.ipynb` ✅
- [x] `docs/eda.md` — hallazgos y decisiones documentados ✅
- [x] `docs/glossary.md` — terminología del EDA documentada ✅

#### Phase 2.2 — Preprocessing ✅

**CSIC 2010:**

| Script | Dataset | Features | Estado |
|---|---|---|---|
| `preprocess_csic_v1.py` | `features.parquet` | 15 | ✅ |
| `preprocess_csic_v2.py` | `features_v2.parquet` | 17 | ✅ |
| `preprocess_csic_v3.py` | `features_v3.parquet` | 22 | ✅ |
| `preprocess_csic_v4.py` | `features_v4.parquet` | 23 | ✅ versión final |

**UNSW-NB15:**

- [ ] `preprocess_unsw.py` — pendiente (EDA completado, listo para implementar)

---

### Phase 3 — Training + MLflow :material-progress-clock:

**Estado:** Modelo A concluido — Modelo B en progreso

#### Phase 3.1 — Modelo A — CSIC 2010 ✅

**Estado:** concluido (2026-04-13)

Entrenamos y refinamos el modelo de detección de ataques web a lo largo de 7 iteraciones de feature engineering. Ver [Modelo A](model_a/index.md) para el detalle completo.

**Resultado final:**

| Métrica | Valor | Target | Estado |
|---|---|---|---|
| Recall | 0.953 | 0.95 | ✅ |
| Precision | 0.793 | 0.85 | ❌ |
| ROC-AUC | 0.968 | — | — |
| FP | 936 | ~630 | ❌ |

**Decisión:** se acepta Precision 0.793 como techo práctico del enfoque de features de campos HTTP individuales. Los 936 FP restantes requieren parseo semántico de valores de parámetros o features de sesión — fuera del scope del MVP.

**Mejor modelo:** LightGBM con `min_recall_val=0.955`, threshold calibrado 0.2573.

**Runs MLflow (experimento `mlsec-model-a`):** 28 runs totales — baseline + v2 a v7.

**Entregables:**

- [x] `src/mlsec/models/train_model_a.py` ✅
- [x] `src/mlsec/data/preprocess_csic_v1.py` → `preprocess_csic_v4.py` ✅
- [x] `notebooks/experiments/csic2010_feature_analysis_v1.ipynb` → `v7.ipynb` ✅
- [x] Métricas documentadas en `docs/model_a/` ✅
- [x] MLflow runs loggeados con parámetros, métricas y threshold ✅

#### Phase 3.2 — Modelo B — UNSW-NB15 :material-progress-clock:

**Estado:** en progreso

**Qué sigue:**

- Implementar `preprocess_unsw.py` con las decisiones del EDA
- Entrenar baseline (RF, XGBoost, LightGBM)
- Iterar features hasta F1 ≥ 0.88 / ROC-AUC ≥ 0.95
- Integrar MLflow desde el primer run

**Entregables:**

- [ ] `src/mlsec/data/preprocess_unsw.py`
- [ ] `data/processed/unsw_nb15/features.parquet`
- [ ] `src/mlsec/models/train_model_b.py`
- [ ] Baseline documentado en `docs/model_b/`

#### Phase 3.3 — MLflow tracking ✅ (parcial)

MLflow integrado desde v3 de Modelo A. Backend SQLite en `mlflow.db`. Experimento `mlsec-model-a` con 28 runs.

- [x] MLflow instalado (v3.11.1) ✅
- [x] Runs loggeados con parámetros, métricas y threshold ✅
- [ ] Modelo B runs pendientes

---

### Phase 4 — Optimización + Airflow :material-progress-clock:

**Estado:** en progreso — DAG de Modelo A funcionando

#### Phase 4.1 — Airflow local (dev) :material-progress-clock:

Airflow instalado en entorno separado (`.venv-airflow`, Python 3.12) para no interferir con las dependencias de ML. Los DAGs invocan los scripts de `.venv` como subprocesos — Airflow actúa como orquestador puro.

**Entregables:**

- [x] Airflow 2.10.4 instalado en `.venv-airflow` ✅
- [x] `dags/dag_model_a.py` — pipeline completo `verify_data → preprocess → train → evaluate` ✅
- [x] `src/mlsec/models/train_model_a_pipeline.py` — script de training con MLflow para el DAG ✅
- [ ] `dags/dag_model_b.py` — pipeline Modelo B pendiente
- [ ] Hyperparameter tuning (GridSearch / Optuna)

**Cómo levantar:**

```bash
# Terminal 1
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow webserver --port 5080 --debug

# Terminal 2
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow scheduler 2>&1 | grep -v "SIGSEGV\|Worker (pid"
```

Ver [documentación de Airflow](airflow.md) para el detalle completo.

#### Phase 4.2 — Docker (producción) :material-lock:

!!! info "MLflow pasa a Docker en esta fase"
    En Phase 4.2, Airflow y MLflow se dockerizan para tener URLs estables entre servicios.

    ```
    services:
      mlflow            ← tracking server (puerto 5000)
      airflow-webserver ← UI de Airflow (puerto 8080)
      airflow-scheduler
      postgres          ← backend store compartido (MLflow + Airflow)
    ```

**Entregables:**

- [ ] `docker-compose.yml` con MLflow + Airflow + Postgres
- [ ] Model registry en MLflow

---

### Phase 5 — API de inferencia :material-lock:

**Entregables:**

- [ ] FastAPI endpoint para predicciones offline
- [ ] Input validation
- [ ] Logging de predicciones

---

## Flujo de trabajo de desarrollo

```
Phase 1 ✅   Definición + descarga de datasets
Phase 2 ✅   EDA ✅ → Preprocessing ✅
Phase 3 🔄   Training — Modelo A ✅ concluido → Modelo B en progreso
Phase 4 🔄   Airflow local ✅ dag_model_a → dag_model_b pendiente → Docker 🔒
Phase 5 🔒   API de inferencia
```
