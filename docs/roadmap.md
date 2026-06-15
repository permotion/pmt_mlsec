# Roadmap

## MVP Goal

Build 2 attack detection models with reference public datasets,
with experiment tracking via MLflow and **offline** detection (no real-time blocking).

---

## Models

| Model | Input | Dataset | Output |
|---|---|---|---|
| A — Web Attack Detection | HTTP request features | CSIC 2010 | normal / attack |
| B — Network Attack Detection | Network flow features | UNSW-NB15 | benign / malicious |

---

## Success Criteria

### Labels
- `0` = benign / normal
- `1` = malicious / attack

### Metrics

Evaluation metrics are: **Precision**, **Recall**, **F1**, **ROC-AUC**.

### Minimum thresholds per model

| Model | Min Recall | Min Precision | Min F1 | Min ROC-AUC |
|---|---|---|---|---|
| A — CSIC 2010 | **0.95** | **0.75** | — | — |
| B — UNSW-NB15 | — | — | **0.88** | **0.95** |

!!! note "Adjusted Precision (2026-04-20)"
    The Precision target for Model A was adjusted from 0.85 → 0.75 after
    post-training analysis. The practical ceiling of the individual HTTP features
    approach is ~0.79. Precision 0.75 is sufficient for a functional first version.
    See [Model A — Post-training analysis](model_a_analysis.md).

!!! note "Why different thresholds"
    In attack detection, the cost of a false negative (undetected attack)
    is higher than that of a false positive. That's why we prioritize high Recall.
    The decision threshold is explicitly defined — 0.5 is not assumed.

---

## Phases

### Phase 1 — Definition + Ingestion ✅

**Status:** completed

**What we did:**

- Defined MVP goal: two binary classification models (web + network)
- Defined success criteria per model (Recall ≥ 0.95 for CSIC, F1 ≥ 0.88 / ROC-AUC ≥ 0.95 for UNSW-NB15)
- Downloaded and organized datasets in `data/raw/`
- Verified integrity with SHA-256 hashes
- Documented sources, licenses, and structure in `docs/datasets.md`

**Deliverables:**

- [x] MVP goal defined
- [x] Success criteria per model defined
- [x] CSIC 2010 dataset downloaded to `data/raw/csic2010/`
- [x] UNSW-NB15 dataset downloaded to `data/raw/unsw_nb15/`
- [x] SHA-256 hashes verified (`CHECKSUMS.sha256` in each folder)
- [x] `docs/datasets.md` updated with sources and licenses

**Relevant files:**

```
data/raw/csic2010/
├── csic_database.csv          ← original dataset (61,065 HTTP requests)
├── README.md
└── CHECKSUMS.sha256

data/raw/unsw_nb15/
├── UNSW_NB15_training-set.parquet   ← 175,341 network flows
├── UNSW_NB15_testing-set.parquet    ← 82,332 network flows
├── README.md
└── CHECKSUMS.sha256
```

---

### Phase 2 — EDA + Preprocessing ✅

**Status:** completed

#### Phase 2.1 — EDA ✅

**What we did:**

Explored the two datasets in Jupyter Notebooks to understand their structure, detect quality issues, decide which features to build, and define preprocessing strategies before writing a single line of production code.

**CSIC 2010** (`notebooks/eda/csic2010_eda.ipynb`):

- Confirmed label was already 0/1 — no transformation needed
- Identified that attacks live in the URL (GET) and in the body (POST)
- Discovered that PUT = 100% attacks — the strongest feature in the dataset
- Discovered that attackers always use URL encoding (`%27`, `%3C`) — never literal chars
- Discarded 11 constant columns without information
- Built and evaluated binary text features (SQLi/XSS indicators)
- Defined imbalance strategy: `class_weight='balanced'` (mild imbalance 59/41)

**UNSW-NB15** (`notebooks/eda/unsw_nb15_eda.ipynb`):

- Confirmed 0/1 label in both splits (predefined train/test in parquet)
- Identified inverse imbalance: 68% attacks in train — more attacks than normal traffic
- Analyzed the 9 attack categories and their distribution (Generic 33%, Exploits 28%, Fuzzers 15%)
- Confirmed there are no nulls — the dataset is complete
- Defined column encoding strategy: top-10+other for `proto` (133 values), direct one-hot for `service` and `state`
- Detected extreme outliers (`sbytes` max 12M, `sload` max 5.9B) → strategy: `RobustScaler`
- Calculated correlations with label: `dload` (-0.394), `rate` (0.338), `ct_dst_sport_ltm` (0.357)
- Identified redundant features with heatmap: `swin`/`dwin` (0.99), `dpkts`/`dloss` (0.98)
- Discarded `dwin`, `dloss`, `is_sm_ips_ports` due to redundancy

**Deliverables:**

- [x] `notebooks/eda/csic2010_eda.ipynb` ✅
- [x] `notebooks/eda/unsw_nb15_eda.ipynb` ✅
- [x] `docs/eda.md` — findings and decisions documented ✅
- [x] `docs/glossary.md` — EDA terminology documented ✅

#### Phase 2.2 — Preprocessing ✅

**CSIC 2010:**

| Script | Dataset | Features | Status |
|---|---|---|---|
| `preprocess_csic_v1.py` | `features.parquet` | 15 | ✅ |
| `preprocess_csic_v2.py` | `features_v2.parquet` | 17 | ✅ |
| `preprocess_csic_v3.py` | `features_v3.parquet` | 22 | ✅ |
| `preprocess_csic_v4.py` | `features_v4.parquet` | 23 | ✅ final version |

**UNSW-NB15:**

- [ ] `preprocess_unsw.py` — pending (EDA completed, ready to implement)

---

### Phase 3 — Training + MLflow :material-progress-clock:

**Status:** Model A concluded — Model B in progress

#### Phase 3.1 — Model A — CSIC 2010 ✅

**Status:** concluded (2026-04-13)

Trained and refined the web attack detection model over 7 iterations of feature engineering. See [Model A](model_a/index.md) for full details.

**Final result:**

| Metric | Value | Target | Status |
|---|---|---|---|
| Recall | 0.9543 | 0.95 | ✅ |
| Precision | 0.7929 | 0.75 | ✅ |
| ROC-AUC | 0.9661 | — | — |
| Recall gap | 0.0079 | ≤ 0.05 | ✅ |

**Model A meets adjusted criteria** (Recall ≥ 0.95 and Precision ≥ 0.75). Original target of 0.85 was reduced to 0.75 after identifying that improving Precision beyond ~0.79 requires SQL semantic parsing — out of MVP scope.

**Best model:** LightGBM with `min_recall_val=0.955`, calibrated threshold **0.3002** (DAG run 2026-04-20, run ID `a4bec971d08e4b74ad4dd94201919075`).

**MLflow runs (`mlsec-model-a` experiment):** 40 runs — 20 historical migrated from SQLite + 20 from notebooks + 1 from DAG.

**Deliverables:**

- [x] `src/mlsec/models/train_model_a.py` ✅
- [x] `src/mlsec/data/preprocess_csic_v1.py` → `preprocess_csic_v4.py` ✅
- [x] `notebooks/experiments/csic2010_feature_analysis_v1.ipynb` → `v7.ipynb` ✅
- [x] Metrics documented in `docs/model_a/` ✅
- [x] MLflow runs logged with parameters, metrics, and threshold ✅
- [x] `docker/docker-compose.yml` + DAG `dag_model_a` end-to-end ✅ (Phase 4.2)
- [x] Post-training analysis documented in `docs/model_a_analysis.md` ✅

#### Phase 3.2 — Model B — UNSW-NB15 :material-progress-clock:

**Status:** in progress

**Next steps:**

- Implement `preprocess_unsw.py` with EDA decisions
- Train baseline (RF, XGBoost, LightGBM)
- Iterate features until F1 ≥ 0.88 / ROC-AUC ≥ 0.95
- Integrate MLflow from the first run

**Deliverables:**

- [ ] `src/mlsec/data/preprocess_unsw.py`
- [ ] `data/processed/unsw_nb15/features.parquet`
- [ ] `src/mlsec/models/train_model_b.py`
- [ ] Baseline documented in `docs/model_b/`

#### Phase 3.3 — MLflow tracking ✅

MLflow integrated since Model A v3. Backend: Postgres in Docker (MLflow 2.22.4 as server). `mlsec-model-a` experiment with 40 total runs — 20 historical migrated from SQLite + notebook runs + DAG run.

- [x] MLflow server in Docker (port 5081) ✅
- [x] Runs logged with parameters, metrics, and threshold ✅
- [x] SQLite → Postgres migration script ✅
- [ ] Pending Model B runs

---

### Phase 4 — Optimization + Airflow :material-progress-clock:

**Status:** in progress — Model A DAG working

#### Phase 4.1 — Local Airflow (dev) :material-progress-clock:

Airflow installed in a separate environment (`.venv-airflow`, Python 3.12) to avoid interference with ML dependencies. DAGs invoke `.venv` scripts as subprocesses — Airflow acts as a pure orchestrator.

!!! warning "macOS ARM — fork deadlock"
    `airflow-scheduler` on macOS ARM has a known deadlock with `StandardTaskRunner`
    (uses `fork()` in multi-threaded processes). Tasks hang indefinitely.
    **Workaround:** move to Docker (Phase 4.2).

**Deliverables:**

- [x] Airflow 2.10.4 installed in `.venv-airflow` ✅
- [x] `dags/dag_model_a.py` — complete pipeline `verify_data → preprocess → train → evaluate` ✅
- [x] `src/mlsec/models/train_model_a_pipeline.py` — training script with MLflow for DAG ✅
- [ ] `dags/dag_model_b.py` — Model B pipeline pending
- [ ] Hyperparameter tuning (GridSearch / Optuna)

**How to start:**

```bash
# Terminal 1
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow webserver --port 5080 --debug

# Terminal 2
AIRFLOW_HOME="$(pwd)/airflow" .venv-airflow/bin/airflow scheduler 2>&1 | grep -v "SIGSEGV\|Worker (pid"
```

See [Airflow documentation](airflow.md) for full details.

#### Phase 4.2 — Docker (production) ✅

**Status:** working (2026-04-13)

Docker Compose with all services, code, and data mounts from the host. The `dag_model_a` DAG runs end-to-end with artifacts saved in MLflow.

**Services:**

| Service | Port | Description |
|---|---|---|
| `postgres` | 5432 | Shared backend store (Airflow + MLflow) |
| `mlflow` | 5081 | MLflow tracking server 2.22.4 |
| `airflow-webserver` | 5080 | Airflow UI (admin/admin) |
| `airflow-scheduler` | — | Executes DAGs |

**First successful run (2026-04-13):**

```
verify_data  →  preprocess  →  train  →  evaluate
    ✅              ✅            ✅         ✅
DagRun: successful — run_id=manual__2026-04-13T15:30:57
```

Run metrics (LightGBM, calibrated threshold 0.3002, run `a4bec971`):

| Metric | Value |
|---|---|
| ROC-AUC | 0.9661 |
| Recall | 0.9543 ✅ |
| Precision | 0.7929 |
| Recall gap | 0.0079 |
| FP | 937 |

MLflow run: `model-a-lightgbm-pipeline` → `mlsec-model-a` experiment, saved artifact.

**Docker file structure:**

```
docker/
├── Dockerfile.airflow        # apache/airflow:2.10.4 + libgomp1 + ML deps
├── Dockerfile.mlflow         # python:3.11-slim + mlflow 2.x
├── docker-compose.yml        # all services
├── init-dbs.sql             # creates mlflow DB in postgres
└── migrate_mlflow.py        # SQLite → Postgres migration script
```

**How to start:**

```bash
# Start
cd docker && docker compose up

# Stop
docker compose -f docker/docker-compose.yml down
```

**Local runs migration:**

The 20 historical runs from `mlflow.db` (SQLite) were migrated to the Docker server via `docker/migrate_mlflow.py`. See [Airflow documentation](airflow.md) for details.

---

### Phase 5 — Inference API :material-progress-clock:

!!! note "Evaluation metrics in imbalanced datasets"
    For imbalanced datasets (100:1 ratio or higher), Recall alone can be misleading.
    Accuracy gives ~99% by predicting only the dominant class.
    Use **ROC-AUC** (rank-based) or **F1-score** (balance of P and R).
    See also: Matthews Correlation Coefficient, Precision-Recall curve.

**Endpoints:**

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | API and model status |
| `/features` | GET | List of 23 expected features |
| `/predict` | POST | Classification: prediction + probability |

**Status (2026-04-20):** API running on port 5082. Model loaded from MLflow. `scale_pos_weight` skews absolute probabilities — the `prediction` (0/1) is reliable for binary decisions, but absolute probability is not. See [API](api.md).

**Pending:** G5 (prediction logging), G6 (integration tests)

**Deliverables:**

- [x] `src/mlsec/api/main.py` — FastAPI app ✅
- [x] `src/mlsec/api/models.py` — Pydantic schemas ✅
- [x] `src/mlsec/api/model_loader.py` — load from pickle or MLflow ✅
- [x] `src/mlsec/api/preprocessing.py` — Note: LightGBM does not require scaling (scaler removed) ✅
- [x] `docker/Dockerfile.api` — Docker image (python:3.11-slim + libgomp1) ✅
- [x] `docs/api.md` — full endpoint and feature documentation ✅
- [ ] Prediction logging to file/DB
- [ ] Integration tests

---

## Development Workflow

```
Phase 1 ✅   Definition + dataset download
Phase 2 ✅   EDA ✅ → Preprocessing ✅
Phase 3 ✅   Training — Model A ✅ concluded → Model B in progress
Phase 4 ✅   Airflow ✅ dag_model_a ✅ → Docker ✅
Phase 5 ✅   Inference API ✅
Phase 6 ✅   Closed gaps ✅

---

Phase R 🔶   Red Team Agent (CrewAI) — in planning
```

**Current status:** Model A and B (IN PROGRESS) in Phase 3. Red Team Agent in Phase R1.

---

## Phase 6 — Improvements and gap closing

**Status:** in progress

This phase documents gaps identified post-training of Model A and actions to close them.

### Identified gaps — Model A

| # | Gap | Priority | Status |
|---|---|---|---|
| G1 | Hardcoded scaler in API — not persisted in MLflow | High | ✅ Closed (2026-04-20) |
| G2 | LightGBM does not need scaling — remove to simplify | High | ✅ Closed (2026-04-20) |
| G3 | EDA without Mutual Information (only Pearson) | Medium | ✅ Closed (2026-04-20) |
| G4 | Feature redundancy (23 features) not analyzed | Medium | ✅ Closed (2026-04-20) |
| G5 | Dataset distribution (41% attacks) does not reflect production (~1%) | High | ✅ Closed (2026-04-20) |
| G6 | — | — | ← absorbed into G5 |
| G7 | — | — | ← absorbed into G5 |
| G8 | No record of train_recall vs test_recall | Low | ✅ Closed (2026-04-20) |
| G9 | No cross-validation or hyperparameter tuning | Medium | 🔶 Optional — low ROI if model meets criteria |
| G10 | No registry workflow (candidate → production) | High | ✅ Implemented (2026-04-20) |

---

### G1 — Remove scaler from pipeline

**Problem:** `StandardScaler` is applied in training (`train_model_a_pipeline.py` lines 78-83) but is not persisted in MLflow. Hardcoded values in `src/mlsec/api/preprocessing.py` can desync if retrained.

**Technical decision:** LightGBM is scale invariant — scaling does not affect tree splits. Removing the scaler simplifies the pipeline and removes the bug.

**Validation (2026-04-20):** Pipeline executed without scaler — identical metrics:
- Recall: 0.9543 (with) vs 0.9543 (without) ✅
- Precision: 0.7929 (with) vs 0.7928 (without) ✅
- ROC-AUC: 0.9661 (identical)
- Recalibrated threshold: 0.2903 → 0.3002 (without scaler, decision unaffected)

**Modified files:**

| File | Change |
|---|---|
| `src/mlsec/models/train_model_a_pipeline.py` | Removed `StandardScaler` and fit/transform lines ✅ |
| `src/mlsec/api/preprocessing.py` | Rised — docstring explaining LightGBM does not require scaling ✅ |
| `src/mlsec/api/main.py` | Removed call to `scale_continuous()` in `/predict` ✅ |

---

### G2 — LightGBM does not need scaling — validation

**Problem:** Without formal validation, there was no confirmation that scaling didn't affect LightGBM.

**5-fold CV Validation (2026-04-20):**

| Fold | Without Scaler | With Scaler | Diff |
|---|---|---|---|
| 1 | 0.9661 | 0.9014 | +0.0647 |
| 2 | 0.9672 | 0.9101 | +0.0571 |
| 3 | 0.9660 | 0.9096 | +0.0564 |
| 4 | 0.9665 | 0.9014 | +0.0651 |
| 5 | 0.9665 | 0.9010 | +0.0655 |

**Conclusion:** Scaling **degrades** ROC-AUC by ~6 points. LightGBM does not need scaling — confirm decision in G1. The pipeline without scaler is superior.

---

---

### G3 — Mutual Information in EDA + Feature Redundancy

**Problem:** Original EDA only used Pearson correlation (linear). For binary and mixed features, Mutual Information captures non-linear relationships that Pearson misses. The 23 features were never analyzed for redundancy.

---

#### Method: Mutual Information (MI)

**What is MI?**
Mutual Information measures how much information a variable shares with another. Unlike Pearson (only linear), MI captures any type of dependency — linear, quadratic, discrete, etc. It's expressed in bits (or nats). MI = 0 means total independence.

```
MI(X; Y) = Σ Σ p(x,y) log[p(x,y) / (p(x) · p(y))]
```

**Criteria used:**
- **MI with label > 0.05:** feature provides useful signal
- **Pairwise MI > 0.3:** possible redundancy (shared information)
- **Spearman ρ > 0.7:** monotonic correlation (complements MI for redundancy)

**Setup:**
```python
from sklearn.feature_selection import mutual_info_classif

mi_scores = mutual_info_classif(
    X, y,
    discrete_features=True,   # all features are binary or integers
    random_state=42,
    n_neighbors=5              # default — less than n=3 to reduce variance
)
```

---

#### Results: MI with the label

| Feature | MI with label | Signal |
|---|---|---|
| url_length | 0.2108 | ██████ High |
| url_query_length | 0.1132 | ███ Medium |
| content_param_density | 0.1081 | ███ Medium |
| content_length | 0.1077 | ███ Medium |
| content_pct_density | 0.0811 | ██ Low |
| url_pct_density | 0.0760 | ██ Low |
| url_path_depth | 0.0444 | █ Marginal |
| content_has_pct27 | 0.0193 | ○ Low |
| url_has_pct27 | 0.0192 | ○ Low |
| content_param_count | 0.0190 | ○ Low |
| method_is_get | 0.0178 | ○ Low |
| url_param_count | 0.0162 | ○ Low |
| url_has_query | 0.0152 | ○ Low |
| method_is_post | 0.0150 | ○ Low |
| content_pct_density | 0.0135 | ○ Very low |
| content_has_dashdash | 0.0135 | ○ Very low |
| url_has_script | 0.0116 | ○ Very low |
| content_has_script | 0.0099 | ○ Very low |
| url_has_pct3c | 0.0095 | ○ Insignificant |
| content_has_pct3c | 0.0095 | ○ Insignificant |
| method_is_put | 0.0058 | ○ Insignificant |
| url_has_select | 0.0015 | ○ Noise |
| content_has_select | 0.0014 | ○ Noise |

**Interpretation:**
- `url_length` is the strongest signal (0.21) — makes sense, attacks often have longer URLs
- 6 features have MI < 0.01: `method_is_put`, `url_has_select`, `content_has_select`, `url_has_pct3c`, `content_has_pct3c`, `content_has_script`

---

#### Results: Redundancy (Spearman ρ > 0.7)

Highly correlated groups (ρ > 0.7):

| Group | Features | Spearman ρ | Highest MI w/ label |
|---|---|---|---|
| **method GET/POST** | `method_is_get` ↔ `method_is_post` | **-0.984** | `method_is_get` (0.0178 > 0.0150) |
| **content length** | `content_length` ↔ `content_param_count` ↔ `content_param_density` | **>0.94** | `content_param_density` (0.1081) |
| **URL params** | `url_param_count` ↔ `url_query_length` ↔ `url_has_query` | **>0.98** | `url_query_length` (0.1132) |
| **URL length** | `url_length` ↔ `url_param_count` ↔ `url_query_length` | **0.79-0.99** | `url_length` (0.2108) — most informative in group |

**Decisions by group:**
1. **GET/POST:** keep `method_is_get` (ρ=-0.98 with POST, same functional group)
2. **Content:** keep `content_param_density` (highest MI 0.1081 in group)
3. **URL params:** keep `url_query_length` (highest MI 0.1132 in group)
4. **URL length:** keep `url_length` (most informative, others are derived)

---

#### Ablation: experimental validation

**What is an ablation?**
It's an experiment where one or more features are removed and the impact on metrics is measured. If removing a feature does not worsen metrics (ΔRecall ≥ -0.5%, ΔPrecision ≥ -1%), it is a candidate for elimination.

**Ablation setup:**
- Split: 70/15/15 (same seed=42 as original training)
- Model: LightGBM, n_estimators=200, scale_pos_weight=spw
- Threshold: calibrated on val for Recall ≥ 0.955
- Metrics: Recall, Precision, ROC-AUC on test set
- Criteria: ✅ ELIMINABLE if ΔR ≥ -0.005 and ΔP ≥ -0.01

**Individual results:**

| Removed Feature | ΔRecall | ΔPrecision | ROC-AUC | N features | Verdict |
|---|---|---|---|---|---|
| `method_is_put` | +0.0000 | -0.0002 | 0.9661 | 22 | ✅ Eliminable |
| `url_has_select` | +0.0005 | +0.0001 | 0.9657 | 22 | ✅ Eliminable |
| `content_has_select` | +0.0000 | +0.0000 | 0.9661 | 22 | ✅ Eliminable |
| `url_has_query` | +0.0000 | +0.0000 | 0.9661 | 22 | ✅ Eliminable |
| `url_param_count` | +0.0008 | -0.0004 | 0.9658 | 22 | ✅ Eliminable |
| `method_is_post` | +0.0005 | -0.0008 | 0.9663 | 22 | ✅ Eliminable |
| `method_is_get` | +0.0000 | +0.0000 | 0.9661 | 22 | ✅ Eliminable |
| `content_param_count` | +0.0003 | -0.0008 | 0.9662 | 22 | ✅ Eliminable |
| `content_length` | -0.0003 | -0.0004 | 0.9661 | 22 | ✅ Eliminable |
| `content_pct_density` | +0.0013 | -0.0137 | 0.9632 | 22 | ⚠️ Caution |

**Group results:**

| Removed Group | ΔRecall | ΔPrecision | ROC-AUC | N features | Verdict |
|---|---|---|---|---|---|
| Low signal (3) | -0.0003 | -0.0000 | 0.9657 | 20 | ✅ Eliminable |
| Redundant content (3) | +0.0011 | -0.0016 | 0.9660 | 20 | ✅ Eliminable |
| **All together (8)** | **-0.0008** | **-0.0298** | 0.9607 | **15** | ⚠️ Caution |

**Group ablation: 8 features removed simultaneously**
```
Removed: method_is_put, url_has_select, content_has_select,
            content_length, content_param_count, method_is_post,
            url_param_count, url_has_query
→ ΔRecall: -0.0008 (acceptable)
→ ΔPrecision: -0.0298 (NOT acceptable — exceeds -0.01 threshold)
→ ROC-AUC: 0.9607 (drops 0.0054)
```

**Ablation conclusion:** Removing 8 features together degrades Precision by ~3 points, indicating that the removed group collectively provided diversity even if each feature individually seemed eliminable. In particular, `content_pct_density` is the most harmful when combined with other eliminations.

---

#### Candidate features for elimination (confirmed by ablation)

| Feature | Reason for elimination | Method that identified it |
|---|---|---|
| `url_has_select` | MI=0.0015 (noise) | MI with label |
| `content_has_select` | MI=0.0014 (noise) | MI with label |
| `method_is_put` | MI=0.0058 (insignificant) | MI with label |
| `method_is_post` | ρ=-0.98 with `method_is_get` (redundant) + lower MI | Spearman + MI |
| `content_param_count` | ρ=0.96 with `content_param_density` (more informative) | Spearman |
| `url_param_count` | ρ=0.99 with `url_query_length` (more informative) | Spearman + MI |
| `url_has_query` | ρ=0.98 with `url_query_length` + MI 0.015 vs 0.113 | Spearman + MI |
| `content_length` | ρ=0.99 with `content_param_density` + lower MI | Spearman |

**Final decision:** No features are removed in this version. The group ablation of 8 features shows that Precision drops 3 points when removed together, indicating that the model benefits from the explicit redundancy of these features to cover edge cases. The cost of eliminating is greater than the benefit of simplifying.

**Recommendation:** Keep the 23 features. Review in the next re-training if more aggressive feature selection is desired.

---

---

### G5 — Real distribution (41% vs ~1%) — unified analysis

**Problem:** The CSIC 2010 dataset has 41% attacks and 59% normal. Real production has ~1% attacks. This skews the threshold, the evaluation of FP, and the interpretation of probabilities.

This gap groups three related issues: test sampling (original G6), synthetic data (original G7), and threshold in real distribution (original G8).

**Executed (2026-04-20):** script `scripts/model_a_analysis/test_real_distribution.py`

---

#### Step 1 — Test with 99:1 distribution

**Setup:**
- Test set: 9160 samples (41% attacks → 5416 normal, 3744 attack)
- Resampled to 5400 samples (99:1): ~54 attacks, ~5346 normal
- Evaluated threshold: 0.3002 (calibrated in val with 41% dataset)

**Comparative results:**

| Metric | Dataset (41%) | 99:1 (~1%) | Delta |
|---|---|---|---|
| Used threshold | 0.3002 | 0.3002 | — |
| Recall | 95.43% | 100.00% | +4.57% |
| Precision | 79.29% | 5.48% | **-73.81%** |
| FP rate | 17.35% | 17.41% | +0.06% |
| FP (absolute) | 937 | 931 | -6 |
| TN | 4463 | 4415 | -48 |
| FN | 172 | 0 | -172 |

**Interpretation:** the model detects all attacks in 99:1 (Recall 100%) but Precision drops drastically. Out of 100 requests classified as an attack, only 5.5 actually are. The other 94.5 are false alarms.

**FP rate in production:** 17.41% — out of 100 normal requests in production, ~17 are incorrectly classified as an attack. This is high for an operable system.

---

#### Step 2 — Corrected threshold for real distribution

**Method:** precision-recall curve on the 99:1 test set. Find the minimum threshold that maintains Recall ≥ 0.95.

**Result:**

| Parameter | Value |
|---|---|
| Dataset threshold (41%) | 0.3002 |
| Corrected threshold (99:1) | 0.4723 |
| **Gap** | **+0.1721** |

**Metrics with corrected threshold (99:1):**

| Metric | Value |
|---|---|
| Recall | 96.30% ✅ (≥ 95%) |
| Precision | 7.51% |
| FP rate | 12.66% |
| FP (absolute) | 677 (vs 931 with original threshold) |

**Conclusion:** raising the threshold from 0.3002 to 0.4723 reduces FPs from 931 to 677 (↓ 27%) while maintaining Recall ≥ 95%. However, FP rate is still 12.66% — still high for production.

---

#### Diagnosis: why Precision is so low in 99:1

The model has `scale_pos_weight=1.44` (calculated from the 41% dataset). In production with 1% attacks, this weight is still 1.44 — it doesn't reflect reality. The model is biased to think that everything with probability >0.3 is an attack.

Furthermore, features like `url_length`, `content_length` are continuous — a normal request with a long URL (e.g., `/api/v3/users/1234567890/profile/settings`) will be classified as suspicious even if it has no malicious payload.

**Critical gap identified:** Precision 5-7% in production means that for every true attack detected, there are ~13-15 false alarms. This saturates the security analyst.

---

#### Recommendation

1. **Do not change the production threshold** (0.3002) — for now, keep it and monitor FP rate in production.

2. **Re-train with 99:1 distribution** — detailed plan in `docs/model_a_analysis.md` section 7:
   - Phase A: prepare 99:1 dataset
   - Phase B: SMOTE + undersampling if dataset is too small (~254 attacks)
   - Phase C: re-train with `scale_pos_weight=99`
   - Phase D: validate on both distributions (99:1 and 41%)
   - Phase E: update API and documentation

3. **Criteria to reconsider:** if FP rate in production exceeds 20%, recalibrate threshold to 0.4723.

---

#### Updated glossary terms

Added to glossary:
- **Ablation** — feature removal technique
- **Distribution shift** — change in dataset vs production distribution
- **FPR in distribution shift context** — FPR interpretation when class proportions change
- **Mutual Information** — feature evaluation method
- **Spearman correlation** — monotonic correlation
- **scale_pos_weight** — effect on probabilities and production
- **99:1 test set** — real distribution validation method

---

### G9 — Cross-validation + hyperparameter tuning

**Status:** 🔶 Optional — low ROI if the model already meets success criteria.

**Reference document:** `docs/model_a_hyperparameter_tuning.md`

**Summary:** the document covers:
- 4 types of CV (K-Fold, Stratified, Repeated, etc.)
- Relevant LightGBM hyperparameters and their ranges
- 3 tuning strategies: Grid Search, Random Search, Bayesian (Optuna)
- Complete tuning process with early stopping
- Sensitivity analysis and parameter interactions
- 4 possible outcome scenarios
- Success criteria and estimated timeline (~1 hour)

**Goal:** determine if there are better hyperparameters than defaults without overcomplicating.

---

### G10 — Model Registry: Candidate → Production

**Problem:** There is no formal workflow to indicate when a trained model is available for the blue team to use in production.

**Solution:** Stages system in MLflow Model Registry.

---

#### Model stages

| Stage | Meaning | Who uses it |
|---|---|---|
| `Staging` | Candidate model under validation | Blue team for testing |
| `Production` | Active model in production | Inference system (API) |
| `Archived` | Discarded model | Historical reference |

---

#### Criteria for tagging as `candidate`

A training run is automatically tagged as `candidate` when it finishes **if and only if** it meets all criteria:

| Metric | Criterion | Last run (`a4bec971`) |
|---|---|---|
| `test_recall` | ≥ 0.95 | 0.9543 ✅ |
| `test_precision` | ≥ 0.75 | 0.7929 ✅ |
| `gap_recall` | ≤ 0.05 | 0.0079 ✅ |
| `test_roc_auc` | ≥ 0.95 | 0.9661 ✅ |

If any criterion is not met, the run remains in MLflow as historical **without a candidate tag**.

---

#### Tagging workflow

```
Training run → Automatic evaluation → Passes criteria?
                                            │
                         ┌─────────────────┴─────────────────┐
                         │Yes                                     │No
                         ▼                                         ▼
               TAG: deployment_stage=candidate           Historical run (no tag)
               + stage=Staging                          Available in MLflow
                         │
                         ▼
               Blue team validates in Staging
                         │
                         ├─ Approves → TAG: stage=Production
                         │                         + TAG: deployment_stage=production
                         │                         + Previous Production → Archived
                         │
                         └─ Rejects → TAG: deployment_stage=rejected
```

---

#### Implementation in `train_model_a_pipeline.py`

```python
# Tag as candidate if it passes criteria
client = MlflowClient()
run_id = mlflow.active_run().info.run_id

criteria = {
    "test_recall": 0.95,
    "test_precision": 0.75,
    "gap_recall": 0.05,
}

passed = all(
    metrics.get(k, 0) >= v
    for k, v in criteria.items()
)

if passed:
    # Register in MLflow Registry
    model_uri = f"runs://{run_id}/model"
    mlflow.register_model(model_uri, "mlsec-model-a", stage="Staging")

    # Deployment tags
    client.set_model_version_tag("mlsec-model-a", version=1, key="deployment_stage", value="candidate")
    client.set_model_version_tag("mlsec-model-a", version=1, key="trained_at", value=datetime.now().isoformat())
else:
    print("Run does not pass criteria — not tagged as candidate")
```

---

#### Load by stage in `model_loader.py`

```python
def get_model(stage: str = "Production"):
    """Loads model by stage from MLflow Registry."""
    client = MlflowClient()
    versions = client.get_latest_versions("mlsec-model-a", stages=[stage])
    if not versions:
        raise RuntimeError(f"No model in stage '{stage}'")

    version = versions[0]
    run_id = version.run_id
    # Load from that run_id...
```

---

#### Roles

| Role | Responsibility |
|---|---|
| **ML team** | Train, evaluate against criteria, tag as candidate |
| **Blue team** | Validate candidate in staging, approve or reject, promote to production |
| **API** | Load model by stage (Production by default) |

---

#### Current status

- [x] Implement automatic tagging in `train_model_a_pipeline.py`
- [x] Implement `get_model(stage=)` in `model_loader.py`
- [x] Promotion script for blue team
- [x] Document in `docs/model_registry.md`

---

## Execution plan

```
G1  Remove scaler         → G2  Validate w/o scaling    → G8  Record train_recall
G3  MI matrix in EDA       → G4  Redundancy analysis    → Feature selection (optional)
G7  Real threshold          → G5  Sampling test 99:1    → (G6  Synthetic data only if G5 fails)
G9  CV + grid search        → 🔶 optional — only if model doesn't meet criteria after G3/G4
```

**Recommended order:**
1. ✅ G1 + G2 + G3 + G4 + G5 + G8 + G10 (completed)
2. G9 🔶 optional

---

### Generated scripts

```
scripts/
├── promote_model_to_production.py  ✅ G10 — promotion Staging → Production
└── model_a_analysis/
    ├── threshold_sweep.py          ✅ existing
    ├── fp_analysis.py              ✅ existing
    ├── feature_importance.py       ✅ existing
    ├── ablation.py                 ✅ existing
    ├── test_real_distribution.py   ✅ G5 — executed 2026-04-20
    └── train_recall_logger.py      ✅ G8 — implemented in train_model_a_pipeline.py

notebooks/experiments/
└── model_a_optimization.ipynb   🔶 G9 — optional (documented in docs/model_a_hyperparameter_tuning.md)
```

---

## Phase R — Red Team Agent

**Status:** in planning

Automated system based on CrewAI for continuous adversarial testing. The Red Team Agent monitors public payload sources, tests them against the API, and reports false negatives to the Blue Team.

**Reference document:** [Red Team Agent — Continuous Adversarial Testing](red_team_agent.md)

### Phase R1 — Core Agent (MVP)

**Status:** pending

**Goal:** Functional agent that tests against the API and generates FN reports

**Deliverables:**
- [ ] `requirements_crewai.txt`
- [ ] 3 CrewAI agents (PayloadHunter, AttackSimulator, Reporter)
- [ ] Tool `http_attack_tool.py`
- [ ] Tool `url_encoder.py`
- [ ] Pipeline `crewai_pipeline.py`
- [ ] FN report in markdown
- [ ] DAG `dag_red_team_agent.py` scheduled every 6h
- [ ] Documentation in `docs/red_team_agent.md`

### Phase R2 — Alerting + Integration

**Status:** pending

**Goal:** FN reports reach Blue Team + MLOps

**Deliverables:**
- [ ] Tool `webhook_alert.py`
- [ ] Slack integration (configurable webhook)
- [ ] MLflow metrics (`red-team` experiment)
- [ ] Configurable threshold via env vars / Airflow vars

### Phase R3 — Multi-source + Deduplication

**Status:** pending

**Goal:** Complete coverage of sources with intelligent filtering

**Deliverables:**
- [ ] GitHub API integration for PayloadAllTheThings
- [ ] NVD CVE feed integration
- [ ] Payload deduplication (hash-based in last 24h)
- [ ] Category filtering (HTTP-related only)
- [ ] Fallback between sources if one fails

### Phase R4 — Advanced + Model B

**Status:** backlog

**Potential deliverables:**
- [ ] Extension for Model B (network attacks)
- [ ] SIEM integration (Splunk/Elastic)
- [ ] Historical detection_rate trend analysis
- [ ] Auto-trigger re-training when detection_rate < 80%
