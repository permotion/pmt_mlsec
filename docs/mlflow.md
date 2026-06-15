# MLflow

## Installation

MLflow is already installed in the project's virtual environment (version 3.11.1). It is listed in `requirements.txt` as a dependency.

```bash
# Install all project dependencies (includes MLflow)
pip install -r requirements.txt

# Or install only MLflow
pip install mlflow
```

First integration in code: `notebooks/experiments/csic2010_feature_analysis_v3.ipynb`.

## Starting the server

```bash
# From the project root
mlflow ui --backend-store-uri "sqlite:///mlflow.db"
# → http://localhost:5000
```

The backend store is `mlflow.db` (SQLite) in the project root. The file-based store (`mlruns/`) is deprecated in MLflow 3.x.

**Note:** Runs from v3 were created before setting the tracking URI and were left in `notebooks/experiments/mlruns/`. From v4 onwards, all runs go to the `mlflow.db` in the root.

---

## Naming conventions

### Experiments (group runs of the same model)

```
mlsec-model-a          ← all Model A runs
mlsec-model-b          ← all Model B runs
```

### Runs (each individual training)

```
{model}-{algorithm}-{description}

Examples:
  model-a-logreg-baseline
  model-a-rf-feature-selection-v2
  model-b-xgboost-smote
```

---

## What to log in each run

### Parameters (`mlflow.log_param`)
```python
mlflow.log_param("model_type", "RandomForest")
mlflow.log_param("n_estimators", 100)
mlflow.log_param("random_state", 42)
mlflow.log_param("dataset", "unsw_nb15")
mlflow.log_param("threshold", 0.45)
mlflow.log_param("class_weight", "balanced")
```

### Metrics (`mlflow.log_metric`)
```python
mlflow.log_metric("precision", precision)
mlflow.log_metric("recall", recall)
mlflow.log_metric("f1", f1)
mlflow.log_metric("roc_auc", roc_auc)
```

### Artifacts (`mlflow.log_artifact`)
```python
mlflow.log_artifact("confusion_matrix.png")
mlflow.log_artifact("feature_importance.png")
mlflow.sklearn.log_model(model, "model")
```

---

## Complete run example

```python
import mlflow
import mlflow.sklearn

mlflow.set_experiment("mlsec-model-b")

with mlflow.start_run(run_name="model-b-rf-baseline"):
    # Parameters
    mlflow.log_param("model_type", "RandomForest")
    mlflow.log_param("n_estimators", 100)
    mlflow.log_param("dataset", "unsw_nb15")
    mlflow.log_param("threshold", 0.5)

    # Training
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    # Metrics
    mlflow.log_metric("precision", precision_score(y_val, y_pred))
    mlflow.log_metric("recall", recall_score(y_val, y_pred))
    mlflow.log_metric("f1", f1_score(y_val, y_pred))
    mlflow.log_metric("roc_auc", roc_auc_score(y_val, y_proba))

    # Model
    mlflow.sklearn.log_model(model, "model")
```

---

## Model Registry

The deployment workflow uses the **MLflow Model Registry** to manage the model lifecycle.

See the full document at [Model Registry — Deployment Workflow](model_registry.md).

### Stages

| Stage | Description |
|---|---|
| `Staging` | Candidate model — trained and evaluated |
| `Production` | Active model — serving predictions |
| `Archived` | Discarded model — replaced by a new one |

### Candidate criteria (Model A)

| Metric | Minimum |
|---|---|
| `test_recall` | ≥ 0.95 |
| `test_precision` | ≥ 0.75 |
| `gap_recall` | ≤ 0.05 |

### Automatic registration

In `train_model_a_pipeline.py`, upon successful training completion:

```python
# If it passes criteria → register in Staging
mlflow.register_model(f"runs://{run_id}/model", "mlsec-model-a", stage="Staging")

# Tags
client.set_model_version_tag(name, version, "deployment_stage", "candidate")
client.set_model_version_tag(name, version, "trained_at", timestamp)
```

### Promotion script

```bash
# View models in Staging
python scripts/promote_model_to_production.py --list

# Promote to Production
python scripts/promote_model_to_production.py
```

---

## `.gitignore`

```
mlruns/
```

MLflow runs are local. Do not version.
