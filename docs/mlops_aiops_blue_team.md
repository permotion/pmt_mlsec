# MLOps + AIOps + Blue Team — Production Workflow

This document describes the complete workflow between the three teams, from when a model is trained until it is serving predictions in production and the blue team uses it to detect attacks.

---

## Service Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              DOCKER COMPOSE                               │
│                                                                          │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌────────────┐  │
│   │  MLflow     │   │  Airflow    │   │  FastAPI    │   │  nginx     │  │
│   │  :5081      │   │  :5080      │   │  :5082      │   │  :5083     │  │
│   │             │   │  (web+sched)│   │  (predict)  │   │  (artfacts)│  │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬────┘  │
│          │                  │                  │                  │       │
│          │    ┌─────────────┴──────────────────┘                  │       │
│          │    │           shared volume: mlflow-artifacts           │       │
│          └────┼──────────────────────────────────────────────────────┘       │
│               │                                                             │
│          ┌────┴────┐                                                      │
│          │ Postgres │ :5432                                               │
│          │ (shared) │                                                      │
│          └──────────┘                                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Roles

| Role | Responsibility | Tools |
|---|---|---|
| **MLOps** | Train and register candidate models | Airflow (`dag_model_a`) |
| **Blue Team** | Validate, promote and monitor models | MLflow UI, API predict, `promote_model_to_production.py` |
| **AIOps** | Detect anomalous patterns in logs | `dag_batch_inference` |
| **Red Team** | Generate fresh inputs, detect model gaps | CrewAI (`dag_red_team_agent`) |

---

## Full Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MLOPS TEAM                                      │
│                                                                              │
│  1. Trigger dag_model_a from Airflow UI                                      │
│     → http://localhost:5080 → dag_model_a → Play                             │
│                                                                              │
│  2. DAG executes 5 tasks:                                                    │
│     verify_data → preprocess → train → register → evaluate                   │
│                                                                              │
│  3. Task train (critical):                                                   │
│     - Split 70/15/15 → train/val/test                                        │
│     - Trains LightGBM with scale_pos_weight                                  │
│     - Calibrates threshold on val (min_recall=0.955)                         │
│     - Evaluates on test: ROC-AUC, Recall, Precision, FP                      │
│     - Logs to MLflow (params + metrics + logged model with name="model")     │
│                                                                              │
│  4. Task register:                                                           │
│     - Searches for the logged model via search_logged_models(source_run_id)  │
│     - Registers with URI models:/<model_id>                                  │
│     - Sets alias=staging + tag deployment_stage=candidate                    │
│                                                                              │
│  5. If it passes criteria (recall≥0.95, precision≥0.75, gap≤0.05):           │
│     → Registration in MLflow Registry with alias=staging                     │
│                                                                              │
│  6. If it DOES NOT pass criteria:                                            │
│     → Historic run in MLflow (without registration)                          │
│     → Notify the team                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MLFLOW REGISTRY                                 │
│                                                                              │
│  mlsec-model-a                                                             │
│  ├── v4 — Staging (deployment_stage=candidate, alias=staging) ← latest     │
│  ├── v3 — Archived                                                          │
│  ├── v2 — Archived                                                          │
│  └── v1 — Archived                                                          │
│                                                                              │
│  To view: http://localhost:5081 → Models → mlsec-model-a                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BLUE TEAM                                       │
│                                                                              │
│  1. Review models in Staging                                                │
│     → http://localhost:5081 → Models → filter by Stage=Staging              │
│     → View run metrics                                                      │
│                                                                              │
│  2. Validate the model                                                      │
│     - Review Recall, Precision, Gap in MLflow                               │
│     - Test with real traffic via API: POST /predict                         │
│     - Evaluate FP rate in the context of traffic volume                     │
│                                                                              │
│  3. Approve or reject                                                       │
│     Approve → promote to Production                                         │
│     Reject → stick with current Production or request adjustments to MLOps  │
│                                                                              │
│  4. Promote to Production                                                   │
│     $ python scripts/promote_model_to_production.py                         │
│     → v4 Staging → Production                                               │
│     → previous Production → Archived                                        │
│                                                                              │
│  5. Monitor in production                                                   │
│     - Observe FP rate: does it exceed 20%?                                 │
│     - If threshold 0.3002 generates too much noise → recalibrate to 0.4723  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AIOPS TEAM                                     │
│                                                                              │
│  Historical logs analysis with dag_batch_inference                           │
│                                                                              │
│  1. Upload access.log to /opt/airflow/data/uploads/access0.log              │
│                                                                              │
│  2. Trigger dag_batch_inference from Airflow UI                             │
│     → http://localhost:5080 → dag_batch_inference → Play                    │
│                                                                              │
│  3. DAG executes:                                                           │
│     check_log_exists → process_log → send_alert                            │
│                                                                              │
│  4. Alert if attacks > THRESHOLD_ATTACK_COUNT (default: 2)                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RED TEAM AGENT                                  │
│                                                                              │
│  Automated pentester via CrewAI — seeks fresh payloads and tests them        │
│                                                                              │
│  1. The DAG `dag_red_team_agent` runs every 6h (scheduled)                   │
│                                                                              │
│  2. PayloadHunterAgent searches in:                                         │
│     - Exploit-DB (HTTP/SQLi/XSS)                                             │
│     - PayloadAllTheThings (GitHub)                                          │
│     - NVD CVE feeds                                                         │
│                                                                              │
│  3. AttackSimulatorAgent formats each payload as an HTTP request             │
│     and sends it to POST /predict                                            │
│                                                                              │
│  4. ReporterAgent compiles results:                                         │
│     - detection_rate_fresh = detected / total                               │
│     - If FN > RT_FN_THRESHOLD → ALERT Blue Team                             │
│     - FN Report saved in reports/red_team/                                  │
│                                                                              │
│  5. Blue Team receives alert if there are significant gaps                  │
│     → Decides whether to request re-training from MLOps                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API — PREDICTIONS SERVICE                       │
│                                                                              │
│  The model in Production is loaded automatically via get_model()             │
│                                                                              │
│  Endpoint: http://localhost:5082/predict                                    │
│  Docs: http://localhost:5082/docs                                           │
│                                                                              │
│  Threshold used: 0.3002 (41% dataset)                                       │
│  For 99:1 production: 0.4723 (documented, not applied yet)                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step-by-step Detail

### MLOps — Training Trigger

1. Open Airflow UI: http://localhost:5080 (admin / admin)
2. Search for `dag_model_a` in the DAGs list
3. Click the **Play** button (▶) to trigger
4. View progress in **Grid View**:
   - `verify_data` → `preprocess` → `train` → `register` → `evaluate`
5. Click on the run to view logs of each task

**CLI Alternative:**

```bash
cd /Users/permotion/Desktop/repositories/PERMOTION/PMT\ MLSec/docker
docker compose exec airflow-webserver airflow dags trigger dag_model_a
```

---

### dag_model_a — What it does and what output it generates

The `dag_model_a` DAG is the complete training pipeline for Model A. It is defined in `dags/dag_model_a.py`.

#### DAG Tasks

```
verify_data  →  preprocess  →  train  →  register  →  evaluate
```

| Task | What it does | Executed script |
|---|---|---|
| `verify_data` | Verifies that the raw CSV exists in `data/raw/csic2010/` | Inline Python |
| `preprocess` | Generates `features_v4.parquet` from the CSV | `preprocess_csic_v4.py` |
| `train` | Trains LightGBM and logs to MLflow (logged model with name="model") | `train_model_a_pipeline.py` |
| `register` | Registers the model in MLflow Registry if it passes criteria | `train_model_a_pipeline.py --register-only` |
| `evaluate` | Verifies that the feature parquet is fine | Inline Python |

#### Task: `verify_data`

```python
def check_raw_data():
    # Verifies: data/raw/csic2010/csic_database.csv exists
    # If it does not exist → FileNotFoundError, DAG fails
```

Expected log output:
```
Dataset found: .../csic_database.csv (XX.X MB)
```

#### Task: `preprocess`

Executes `preprocess_csic_v4.py` — the feature engineering script.

Expected log output:
```
Shape: (61065, 24) | Attack rate: 41.2%
features_v4.parquet written to data/processed/csic2010/
```

If the parquet already exists and is up-to-date, it does nothing (it is idempotent).

#### Task: `train` — The critical step

Executes `train_model_a_pipeline.py`. This is the main training script.

**Input:** `features_v4.parquet` (61,065 rows × 23 features)

**Internal process:**

1. **Stratified split 70/15/15** (seed=42)
   - Train: ~42,745 samples
   - Val: ~9,160 samples
   - Test: ~9,160 samples

2. **Trains LightGBM** with `scale_pos_weight` (automatic balancing)

3. **Calibrates threshold** on validation set for `min_recall_val=0.955`

4. **Evaluates on test** and computes metrics

5. **Logs to MLflow:** parameters, metrics, artifact

6. **Registers in Model Registry** if it passes candidate criteria

**Expected log output:**

```
Loading features from .../features_v4.parquet ...
Shape: (61065, 24) | Attack rate: 41.2%
Train: 42745 | Val: 9160 | Test: 9160
Training LightGBM ...
Calibrated threshold (min_recall_val=0.955): 0.3002
Train Recall (threshold=0.3002): 0.9622

--- Test results ---
ROC-AUC:   0.9661
Recall:    0.9543  ✅
Precision: 0.7929
FP:        937
Run logged to MLflow — experiment 'mlsec-model-a'
```

**Metrics logged in MLflow:**

| Metric | Description | Expected value |
|---|---|---|
| `test_recall` | Recall on test set | ≥ 0.95 |
| `test_precision` | Precision on test set | ≥ 0.75 |
| `test_roc_auc` | ROC-AUC on test set | ≥ 0.95 |
| `train_recall` | Recall on train set | reference |
| `gap_recall` | `train_recall - test_recall` | ≤ 0.05 |
| `test_fp` | False positives on test | ~900-1000 |

**Parameters logged in MLflow:**

| Parameter | Value |
|---|---|
| `model` | `LightGBM` |
| `n_features` | `23` |
| `min_recall_val` | `0.955` |
| `threshold` | `0.3002` |
| `random_state` | `42` |
| `features_path` | path to parquet |

**Saved artifact:**

- `model/` — the serialized LightGBM model via `mlflow.sklearn.log_model(name="model")` (MLflow 3.x logged model API)

#### Task: `register`

Executes `train_model_a_pipeline.py --register-only`. This step:
1. Searches for the last completed run of the `mlsec-model-a` experiment
2. Verifies that it passes candidate criteria (recall≥0.95, precision≥0.75, gap≤0.05)
3. Searches for the logged model via `search_logged_models(source_run_id=run_id)`
4. Registers with URI `models:/<model_id>` (MLflow 3.x)
5. Sets alias `staging` and tag `deployment_stage=candidate`

**Expected output if it passes:**

```
Latest run: a83d13be2da34ea7a217ff4e1530e4e7
  test_recall:    0.9543
  test_precision: 0.7929
  gap_recall:     0.0079

✅ Model registered: mlsec-model-a v4 (alias=staging, deployment_stage=candidate)
```

**Expected output if it does not pass:**

```
Model does not pass candidate criteria — not registered in Registry
```

Verifies that the feature parquet is fine.

Expected output:
```
features_v4.parquet: 61065 rows, 23 features
Pipeline completed successfully.
```

#### Candidate Criteria — When it is registered in Staging

After training, `register_last_run()` evaluates:

| Metric | Criterion | Check |
|---|---|---|
| `test_recall` | ≥ 0.95 | ✅ if passes |
| `test_precision` | ≥ 0.75 | ✅ if passes |
| `gap_recall` | ≤ 0.05 | ✅ if passes |

**If it passes all criteria:**

```
Model registered in MLflow Registry: mlsec-model-a v6 (stage=Staging, deployment_stage=candidate)
```

**If it DOES NOT pass any criterion:**

```
Model does not pass candidate criteria — not registered in Registry
```

The run remains in MLflow as historical, but it does not appear in the Model Registry. You must review the logs to see which metric failed.

#### How to verify that the DAG worked properly

1. **Airflow UI** → dag_model_a → latest run → all tasks in green ✅

2. **MLflow UI** → http://localhost:5081 → experiment `mlsec-model-a` → latest run:
   - Status: `Finished`
   - Metrics: Recall ≥ 0.95, Precision ≥ 0.75
   - Artifact: `model/` present

3. **Model Registry** → http://localhost:5081 → Models → `mlsec-model-a`:
   - If passed criteria → appears in Stage `Staging`
   - If not passed → does not appear (remains only in historic runs)

### Blue Team — Staging Review

1. Open MLflow UI: http://localhost:5081
2. Go to **Models** → select `mlsec-model-a`
3. Filter by **Stage: Staging**
4. Click on the version → view:
   - Run metrics (Recall, Precision, ROC-AUC, Gap)
   - Calibrated threshold
   - Training date
   - Tags (`deployment_stage`, `trained_at`)

### Blue Team — Promotion to Production

```bash
cd /Users/permotion/Desktop/repositories/PERMOTION/PMT\ MLSec
python scripts/promote_model_to_production.py
```

Or view available models first:

```bash
python scripts/promote_model_to_production.py --list
```

The script:
1. Shows models in Staging and current Production
2. Promotes the latest Staging → Production
3. Archives the previous Production
4. Sets tag `deployment_stage=production`

### AIOps — Batch Inference on logs

1. Copy the log file to the shared folder:
   ```bash
   cp access0.log /Users/permotion/Desktop/repositories/PERMOTION/PMT\ MLSec/data/uploads/
   ```
   (Inside the container it is at `/opt/airflow/data/uploads/access0.log`)

2. Trigger `dag_batch_inference` from Airflow UI

3. View results in the `send_alert` task logs

**Alert threshold configuration:**

Edit `dag_batch_inference.py` line 31:
```python
THRESHOLD_ATTACK_COUNT = 2  # change according to need
```

---

## Post-deploy Monitoring

### What to observe

| Metric | What it measures | Alert Threshold |
|---|---|---|
| FP rate | % of normal requests classified as attack | > 20% |
| Recall | % of real attacks detected | < 0.95 |
| API Latency | Response time of /predict | > 500ms |

### Threshold in production (99:1 distribution)

The current threshold (0.3002) is calibrated for the dataset with 41% attacks. In production with ~1% attacks:

- **FP rate rises to ~17%** (1 out of 6 normal requests marked as an attack)
- **Precision drops to ~5-7%**

If the FP rate exceeds 20%, consider raising the threshold to **0.4723**:

| Threshold | Recall (99:1) | FP rate | Precision |
|---|---|---|---|
| 0.3002 | 100% | 17.4% | 5.5% |
| 0.4723 | 96.3% | 12.7% | 7.5% |

To change the threshold in production, update `THRESHOLD` in `model_loader.py` and rebuild the API image.

---

## System Success Criteria

| Metric | Target | Who measures it |
|---|---|---|
| Recall | ≥ 0.95 | MLOps (training), Blue Team (production) |
| Precision | ≥ 0.75 | MLOps (training), Blue Team (production) |
| FP rate production | < 20% | Blue Team |
| API availability | > 99% | AIOps |
| Response time | < 500ms p95 | AIOps |
| Fresh payloads detection rate | ≥ 85% | Red Team Agent |
| Generated FN report | every cycle (6h) | Red Team Agent |
| Red Team cycle latency | < 10 min | Airflow |

---

## References

- [Project Roadmap](roadmap.md)
- [Model Registry — Deployment Workflow](model_registry.md)
- [Inference API](api.md)
- [MLflow setup](mlflow.md)
- [Red Team Agent — Continuous Adversarial Testing](red_team_agent.md)
- [RACI — Responsibility Matrix](raci_model_lifecycle.md)
