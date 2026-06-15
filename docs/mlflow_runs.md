# How to read an MLflow run

This guide explains how to interpret run information in the `mlsec-model-a` experiment. It is designed for someone with a technical background who needs to understand what they are looking at and what to decide based on MLflow data.

---

## Quick context

Every time a model is trained in this project, MLflow logs a **run**: a complete snapshot of that training. A run contains:

- The **parameters** it was trained with (algorithm, features version, etc.)
- The evaluation **metrics** (ROC-AUC, Recall, Precision, etc.)
- The generated **artifacts** (plots, serialized model)
- System metadata (when it ran, how long it took, from which notebook)

The `mlsec-model-a` experiment groups all Model A (CSIC 2010) runs. To view them:

```bash
# From the project root
mlflow ui --backend-store-uri "sqlite:///mlflow.db"
# → http://localhost:5000 → click on "mlsec-model-a"
```

---

## Anatomy of a run

### Left panel — "About this run"

| Field | What it is | How to use it |
|---|---|---|
| **Run ID** | Unique UUID of the run (e.g., `70c07c5d...`) | To reference the run in code: `mlflow.load_model(f"runs:/{run_id}/model")` |
| **Created at** | Execution timestamp | To know when it was done and sort chronologically |
| **Status** | `Finished` / `Failed` / `Running` | A `Failed` run has unreliable metrics — ignore it |
| **Duration** | Run execution time | Reference for planning re-trainings |
| **Source** | Notebook or script that generated it | To reproduce exactly: open that notebook and re-run |
| **Experiment ID** | Parent experiment ID | Groups all runs of the same model |

### Overview tab — Metrics

The 8 metrics logged in each run:

| Metric | What it measures | MVP Criterion | How to read it |
|---|---|---|---|
| `roc_auc` | Model's ability to separate classes across **all thresholds**. 0.5 = random, 1.0 = perfect | — | Indicates the theoretical quality ceiling. Two models with the same ROC-AUC have the same theoretical separation capacity, even if optimal thresholds vary |
| `recall` | Of all real attacks, how many did it detect? | **≥ 0.95** | The critical security number. 0.952 = detects 95.2% of real attacks — the remaining 4.8% slip through |
| `precision` | Of all triggered alarms, how many were real attacks? | **≥ 0.85** | Measures false alarm noise. 0.713 = out of 10 alarms, 7.13 are real attacks and 2.87 are misclassified normal traffic |
| `f1` | Harmonic mean of Precision and Recall | — | Single number summary when there's no priority between the two metrics. In security we use Recall and Precision separately because their criteria differ |
| `fp` | Absolute False Positive count | — | Translates Precision to concrete terms: 1444 FP = 1444 legitimate requests flagged as attacks per day |
| `fn` | Absolute False Negative count | — | Translates Recall to concrete terms: 179 FN = 179 real attacks that slip through undetected |
| `tp` | True Positives (correctly detected attacks) | — | With FN: `Recall = TP / (TP + FN)` |
| `tn` | True Negatives (correctly classified normal traffic) | — | With FP: `Precision = TP / (TP + FP)` |

!!! tip "How to decide if a run is good"
    The MVP criteria are **Recall ≥ 0.95** and **Precision ≥ 0.85**. Check those two metrics first. If a run doesn't meet Recall ≥ 0.95, it's discarded — no matter how much Precision improves. If it meets Recall but not Precision, there is feature work to be done.

### Overview tab — Parameters

The 10 logged parameters document exactly how the run was trained:

| Parameter | What it documents |
|---|---|
| `model_type` | Algorithm used (e.g., `LightGBM`) |
| `dataset` | Source dataset (`csic2010` or `unsw_nb15`) |
| `features_version` | Preprocessing version (`v1`, `v2`, `v3`...) — indicates which features were available |
| `n_features` | Number of features the model received |
| `random_state` | Random seed — to reproduce the exact same split and model |
| `threshold` | Decision value optimized in validation — the score from which the model classifies as "attack" |
| `min_recall_threshold` | The minimum Recall used to calculate the optimal threshold |
| `split` | Train/val/test split used |
| `class_weight` | Whether class balancing was used |
| `scale_pos_weight` | Scaling factor for positive classes (XGBoost/LightGBM only) |

!!! info "Why `threshold` matters"
    The model doesn't predict "attack" or "normal" directly — it predicts a probability between 0 and 1. The threshold is the cutoff: if probability ≥ threshold → attack. In v3, thresholds are much lower than 0.5 (e.g., 0.15 for RF) because the dataset is imbalanced. If 0.5 were used, Recall would drop significantly. The threshold logged in MLflow is the one that yields Recall ≥ 0.95 on validation.

### Artifacts tab

Artifacts are files generated during the run. For the `mlsec-model-a` experiment:

| Artifact | What it contains | What to use it for |
|---|---|---|
| `confusion_matrix.png` | Visualized TP/FP/TN/FN table | Review error distribution at a glance |
| `feature_importance.png` | Feature ranking by model contribution | Decide which features to explore in the next iteration |
| `model/` | Serialized model (pickle + MLflow metadata) | Load the model for inference: `mlflow.sklearn.load_model(f"runs:/{run_id}/model")` |

To view artifacts: click on the **Artifacts** tab → navigate the file tree → click the image for a browser preview.

### Logged models

At the bottom of the Overview panel is the "Logged models" section. It shows the model registered in the run with its state:

| State | Meaning |
|---|---|
| `Ready` | The model is available for loading and inference |
| (no state) | The model was logged but not registered in the Model Registry |

The `roc_auc` column in this section is the ROC-AUC of the model at the time of logging — useful as a quick reference without opening the full metrics.

---

## How to compare runs

The `mlsec-model-a` experiment table shows all runs together. To make decisions:

1. **Go to http://localhost:5000** → click `mlsec-model-a`
2. **Select the runs to compare** (checkbox on the left)
3. **Click "Compare"** → parallel view of metrics and parameters

The `features_version` column in parameters lets you mentally group runs by iteration:

| features_version | Runs | What changed |
|---|---|---|
| v3 | `model-a-lgbm-features-v3`, `model-a-rf-features-v3`, `model-a-xgboost-features-v3`, `model-a-logreg-features-v3` | + `content_pct_density` vs v2 |

!!! tip "Quick table reading"
    Sort the table by `precision` (click the column header). Runs with the best Precision appear at the top. If they also have `recall` ≥ 0.95, they are candidates for detailed analysis. If none meet both metrics, the work remains in the features.

---

## Current status — mlsec-model-a runs

| Run name | Algorithm | features_version | ROC-AUC | Recall | Precision | FP | Status |
|---|---|---|---|---|---|---|---|
| `model-a-lgbm-features-v3` | LightGBM | v3 | 0.955 | 0.952 ✅ | 0.713 ❌ | 1444 | Best Precision so far |
| `model-a-rf-features-v3` | Random Forest | v3 | 0.950 | 0.947 ❌ | 0.716 ❌ | 1416 | Recall < 0.95 with v3 |
| `model-a-xgboost-features-v3` | XGBoost | v3 | 0.948 | 0.958 ✅ | 0.649 ❌ | 1946 | Recall OK but low Precision |
| `model-a-logreg-features-v3` | Logistic Regression | v3 | 0.777 | 0.977 ✅ | 0.417 ❌ | 5138 | Discarded — does not separate classes |

**Pending gap:** Precision 0.713 → 0.85 = 0.137 left to close. The next iteration (v4) tackles the 935 GET FPs with URL structure analysis.

---

## Summarized decision flow

```
Does the run meet Recall ≥ 0.95?
    ├── No → Lower threshold or review split. Do not push to production.
    └── Yes → Does it meet Precision ≥ 0.85?
                ├── No → Analyze feature importance and FP. Plan next feature iteration.
                └── Yes → Candidate for Model Registry.
                          Validate on test set. Register with mlflow.register_model().
```
