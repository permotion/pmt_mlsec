# Model B — Network Attack Detection

**Dataset:** UNSW-NB15  
**Input:** Network flow features  
**Output:** `0` benign / `1` malicious

---

## MVP Success Criteria

| Metric | Minimum |
|---|---|
| F1 | ≥ 0.88 |
| ROC-AUC | ≥ 0.95 |

---

## Current Status

> [!NOTE]
> **Pending**
> Model B is in the queue. Preprocessing is ready (`preprocess_unsw.py`), but training and experiments have not started yet.
> 
> **Pending:** create `src/mlsec/models/train_model_b.py` and run the baseline.

---

## Completed Preprocessing

**Script:** `src/mlsec/data/preprocess_unsw.py`  
**Outputs:** `data/processed/unsw_nb15/train.parquet` (175,341 × 62), `test.parquet` (82,332 × 62)

Key preprocessing decisions:

| Decision | Justification |
|---|---|
| Scaler: **RobustScaler** | Resistant to outliers — `sbytes` max 12M, `sload` max 5.9B |
| Drop `dwin`, `dloss`, `is_sm_ips_ports` | Redundant with other features |
| Drop `attack_cat` | Only for analysis — not an input feature |
| `proto`: top-10 + 'other' one-hot | 133 unique values — reduction needed |
| `service`, `state`: direct one-hot | Few unique values |
| `DataFrame.align()` | Synchronizes train/test columns after one-hot |

See EDA: `notebooks/eda/unsw_nb15_eda.ipynb`
