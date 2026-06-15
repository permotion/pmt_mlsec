# Model Registry — Deployment workflow

## Overview

This document describes the complete flow for a model to go from training to production, including the blue team's role in validation and promotion.

---

## Key concepts

### MLflow Model Registry

MLflow has a component called **Model Registry** that works as a catalog of versioned models with deployment stages. It replaces the manual handling of pickle files with a structured workflow.

### Stages — MLflow 3.x

Each version of a registered model has an **alias** (replaces `stage` from MLflow 2.x):

| Alias | Meaning | Who sets it |
|---|---|---|
| `staging` | Candidate model, in validation | MLOps (automatic via `set_registered_model_alias`) |
| `production` | Active model, serving predictions | Blue team (manual via `promote_model_to_production.py`) |
| `archived` | Discarded model | Blue team (automatic when promoting another) |

> **Note:** MLflow 2.x used `stage` (Staging/Production/Archived). MLflow 3.x uses `alias`. The `promote_model_to_production.py` script uses `transition_model_version_stage` which internally sets the corresponding alias.

### Runs vs Registered Models

A **run** in MLflow is the record of a training: parameters, metrics, and artifacts.

A **registered model** is a specific version of the artifact that was elevated to a stage. Several runs can produce models with the same version (if re-trained with the same parameters), but the registration is a discrete event.

---

## Complete flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ML TEAM                                      │
│                                                                       │
│  dag_model_a.py                                                        │
│       │                                                                │
│       ▼                                                                │
│  train_model_a_pipeline.py                                            │
│       │                                                                │
│       ├── Trains LightGBM                                             │
│       ├── Evaluates on test set                                       │
│       └── Passes criteria?                                            │
│                 │                                                      │
│        ┌────────┴────────┐                                             │
│        │Yes              │No                                          │
│        ▼                 ▼                                             │
│  search_logged_models(   Historical run in                             │
│    source_run_id)         MLflow (without registration)                 │
│        │                                                                │
│        ▼                                                                │
│  mlflow.register_model(                                            │
│    models:/<model_id>)                                                │
│        │                                                                │
│  set_registered_model_alias("staging")                                │
│        │                                                                │
│  set_model_version_tag("deployment_stage", "candidate")              │
│        │                                                                │
│        ▼                                                                │
│  MLflow Registry:                                                      │
│  mlsec-model-a v4 → alias=staging                                      │
│    deployment_stage=candidate                                          │
│    trained_at=2026-04-21                                              │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         BLUE TEAM                                     │
│                                                                       │
│  1. View models in Staging                                            │
│     $ python scripts/promote_model_to_production.py --list           │
│                                                                       │
│     ┌──────────────────────────────────────────────────────────┐       │
│     │ Ver  Stage  Run ID   Recall  Precision  Gap  Threshold │       │
│     ├───┼──────┼────────┼────────┼──────────┼─────┼──────────┤       │
│     │ 4  │Staging  a83...  0.9543   0.7929   0.0079  0.3002  candidate │       │
│     └──────────────────────────────────────────────────────────┘       │
│                                                                       │
│  2. Validate the model in staging environment                        │
│     - Test with real or historical traffic                            │
│     - Review metrics in MLflow                                        │
│     - Verify the threshold is adequate                                │
│                                                                       │
│  3. Approve the model?                                                │
│           │                                                            │
│    ┌──────┴──────┐                                                     │
│    │Yes          │No → Tag as rejected                                │
│    ▼             ▼                                                     │
│  Promote to    Keep current                                          │
│  Production    Production                                              │
│                                                                       │
│  4. Promote to Production                                              │
│     $ python scripts/promote_model_to_production.py                    │
│     # or specific version:                                             │
│     $ python scripts/promote_model_to_production.py --version 4        │
│                                                                       │
│     Result:                                                            │
│       - v4: Staging → Production                                      │
│       - Previous Production: → Archived                                │
│       - deployment_stage: "production"                                 │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         API (automatic)                               │
│                                                                       │
│  get_model(alias="production")  ← default                             │
│       │                                                                │
│       ▼                                                                │
│  MlflowClient.get_latest_versions("mlsec-model-a", stages=["Production"])│
│       │                                                                │
│       ▼                                                                │
│  Loads model from run artifact                                         │
│                                                                       │
│  Threshold: 0.3002 (from run params)                                  │
│  Prediction: binary (0/1) based on threshold                           │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Candidate criteria

Before registering a model as `Staging`, the training pipeline verifies that the model meets the minimum criteria:

| Metric | Criterion | Source |
|---|---|---|
| `test_recall` | ≥ 0.95 | From the run |
| `test_precision` | ≥ 0.75 | From the run |
| `gap_recall` | ≤ 0.05 | `train_recall - test_recall` |
| `test_roc_auc` | ≥ 0.95 | Reference |

**If it fails any criterion:** the run remains in MLflow as historical, but **is not registered** in the Model Registry. The ML team receives a notification and must decide whether to train with different parameters.

### Why these values?

- **Recall ≥ 0.95**: We detect at least 95% of real attacks. The remaining 5% are false negatives — attacks that pass without an alarm. In security, a false negative is the most expensive.
- **Precision ≥ 0.75**: Out of every 10 alarms, at least 7.5 are real attacks. With 25% false alarms, the system is operable although it generates noise.
- **gap_recall ≤ 0.05**: If the model has 96% Recall in train but 85% in test, it is overfitting. The gap measures overtraining.

---

## Promotion script

Location: `scripts/promote_model_to_production.py`

### View available models

```bash
python scripts/promote_model_to_production.py --list
```

Example output:

```
Models in Staging — experiment 'mlsec-model-a':

| Ver | Stage   | Run ID  | Recall | Precision | Gap   | Threshold |
|-----|---------|---------|--------|-----------|-------|-----------|
| 6   | Staging | a4bec97 | 0.9543 |    0.7929 | 0.0079|    0.3002 |

Current model in Production:
  Version:  5
  Run ID:   70c07c5d
  Recall:   0.9531
  Precision: 0.7912
  Threshold:  0.2903
```

### Promote to Production

```bash
# Promote the latest version in Staging
python scripts/promote_model_to_production.py

# Promote a specific version
python scripts/promote_model_to_production.py --version 6
```

Output:

```
Promoting model v6 to Production:
  Run ID:     a4bec971d08e4b74ad4dd94201919075
  Recall:     0.9543
  Precision:  0.7929
  ROC-AUC:    0.9661
  Gap recall: 0.0079
  Threshold:  0.3002

  Previous Production (v5) → Archived

  v6 → Production ✅

The API can load this model with get_model(stage='Production')
```

---

## Blue team role

### Responsibilities

1. **Review models in Staging** — log into MLflow UI or use `--list` to see what's pending
2. **Validate the model** — test with real traffic, review FP rate, confirm MLflow metrics are consistent with what's observed
3. **Approve or reject** — if okay, promote to Production; if not, keep the current one or ask the ML team to adjust
4. **Monitor** — after promotion, observe the model's behavior in production

### Approval criteria

The blue team does not need to reproduce MLflow metrics — those were already validated in training. What they must review is:

- Is the chosen threshold operable for the traffic volume?
- Are the observed FP rates acceptable?
- Is there anything in production traffic that the dataset doesn't cover?

### Validation time

There is no defined SLA. The model remains in Staging until the blue team promotes or rejects it.

---

## How the API loads

The API (`src/mlsec/api/model_loader.py`) loads the model by stage:

```python
from mlsec.api.model_loader import get_model

# Loads Production by default
model, scaler, threshold = get_model()

# For staging (testing):
model, scaler, threshold = get_model(stage="Staging")
```

**Important:** `get_model()` searches in this order:

1. **MLflow Registry** (if `MLFLOW_TRACKING_URI` is configured) → loads by stage
2. **Local pickle fallback** (`models/model_a_lightgbm.pkl`) → if the Registry doesn't have the requested stage

In the production Docker environment, `MLFLOW_TRACKING_URI` points to the MLflow server, so the API always uses the Registry.

---

## Metadata for each version

Each registered model has tags for tracking:

| Tag | Description | Example |
|---|---|---|
| `deployment_stage` | Model's role in the workflow | `candidate`, `production`, `rejected` |
| `trained_at` | Training timestamp | `2026-04-20T14:30:00.000000` |
| `promoted_at` | Promotion to Production timestamp | `2026-04-20T16:00:00.000000` |

These tags are set during registration (candidate) and promotion (production).

---

## Version history

| Version | Alias | Recall | Precision | Threshold | Promoted by |
|---|---|---|---|---|---|
| v4 | staging | 0.9543 | 0.7929 | 0.3002 | — (current candidate) |
| v3 | — | 0.9543 | 0.7929 | 0.3002 | Archived |
| v2 | — | 0.9531 | 0.7912 | 0.2903 | Archived |
| v1 | — | 0.9528 | 0.7905 | 0.2887 | Archived |

---

## Common errors

### "No model in Staging"

Cause: the last training didn't pass the candidate criteria.
Solution: review the run in MLflow → verify why it didn't pass the criteria.

### "No model in Production"

Cause: no model was ever promoted, or the only Production was archived.
Solution: promote a model from Staging.

### "Production model doesn't load"

Cause: the artifact might be in an inaccessible URI (e.g. inside the MLflow container).
Solution: verify `MLFLOW_ARTIFACT_PROXY` in `model_loader.py`. The artifact is downloaded through the nginx proxy (`nginx-artifacts:80`).

---

## Quick reference

```bash
# View models in Staging and Production
python scripts/promote_model_to_production.py --list

# Promote latest Staging version to Production
python scripts/promote_model_to_production.py

# Promote specific version
python scripts/promote_model_to_production.py --version 6

# View MLflow UI
mlflow ui --backend-store-uri "sqlite:///mlflow.db"
# → http://localhost:5000
```
