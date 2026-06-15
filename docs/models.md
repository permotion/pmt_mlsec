# Models

## Design decisions

### Unified labels
- `0` = benign / normal
- `1` = malicious / attack

### Decision threshold
The threshold **is not assumed to be 0.5**. It is determined by ROC/PR curve optimizing the success criteria of each model.

### Validation strategy
- Stratified split (preserves class distribution)
- `train/val/test`: 70% / 15% / 15%
- Reproducibility: `random_state=42` in all splits

---

## Model A — Web Attack Detection

**Dataset:** CSIC 2010  
**Input:** Features extracted from HTTP requests  
**Output:** `0` (normal) / `1` (attack)

### Success criteria

| Metric | Minimum threshold |
|---|---|
| Recall | ≥ 0.95 |
| Precision | ≥ 0.85 |

### Dataset info (post-EDA)

| Field | Value |
|---|---|
| Total records | 61,065 |
| Original columns | 17 |
| Normal (0) | 36,000 (59%) |
| Attack (1) | 25,065 (41%) |
| GET requests | ~43,088 (70.6%) |
| POST requests | ~18,977 (29.4%) |

### Class imbalance strategy

Mild imbalance (59/41) — does not require SMOTE.
Use `class_weight='balanced'` in the model.

### Where the attacks live

- **GET** → the attack is in the `URL` (query string)
- **POST** → the attack is in `content` (request body)

### Discarded columns (post-EDA)

| Column | Reason |
|---|---|
| `Unnamed: 0` | Redundant with label |
| `host` | 2 values, no useful signal |
| `connection` | 2 values, no useful signal |
| `language` | Constant — 1 single value |
| `User-Agent` | Constant — 1 single value |
| `Pragma` | Constant — 1 single value |
| `Cache-Control` | Constant — 1 single value |
| `Accept` | Constant — 1 single value |
| `Accept-encoding` | Constant — 1 single value |
| `Accept-charset` | Constant — 1 single value |
| `content-type` | Constant among non-nulls — 1 single value |

### Nulls — strategy

| Column | Nulls | Strategy |
|---|---|---|
| `content`, `lenght`, `content-type` | 70.56% | Do not impute — they are NaN by design in GETs |
| `Accept` | 0.65% | Impute with mode or discard |

### Candidate features (initial post-EDA)

| Feature | Source | Type | Notes |
|---|---|---|---|
| `method_is_put` | `Method` | Binary | **100% attacks** — most powerful feature |
| `method_is_post` | `Method` | Binary | 54% attack rate |
| `url_length` | `URL` | Numeric | Attack URLs are usually longer |
| `content_length` | `content` | Numeric | 0 in GETs, present in POSTs |
| `url_has_sq` | `URL` | Binary | Presence of `'` — SQLi |
| `url_has_lt/gt` | `URL` | Binary | Presence of `<>` — XSS |
| `url_has_dashdash` | `URL` | Binary | Presence of `--` — SQLi |
| `url_has_select` | `URL` | Binary | SQL keyword |
| `url_has_union` | `URL` | Binary | SQL keyword |
| `url_has_script` | `URL` | Binary | XSS keyword |
| `url_has_pct27` | `URL` | Binary | URL-encoded `'` |
| `content_has_*` | `content` | Binary | Same indicators in POST body |

> Exact correlations with the label: pending section 7-8 of the notebook.

### Models to evaluate (in order)

1. **Baseline:** Logistic Regression
2. Random Forest
3. Gradient Boosting (XGBoost / LightGBM)

### Training results — Phase 3.1

Stratified split 70/15/15 — `random_state=42`.  
Script: `src/mlsec/models/train_model_a.py`

#### Logistic Regression (baseline)

| Split | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| Validation | 1.000 | 0.411 | 0.582 | 0.739 |
| **Test** | **1.000** | **0.411** | **0.582** | **0.761** |

| Criterion | Result | Status |
|---|---|---|
| Recall ≥ 0.95 | 1.000 | ✅ |
| Precision ≥ 0.85 | 0.411 | ❌ |

**Diagnosis:** the model predicts everything as an attack. With 0.76 ROC-AUC it doesn't have enough capacity to separate classes — the optimal threshold for Recall ≥ 0.95 collapses to such a low value that it classifies all records as attacks. Precision = proportion of attacks in the dataset (41%).

#### Random Forest (200 estimators)

| Split | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| Validation | 0.950 | 0.649 | 0.771 | 0.936 |
| **Test** | **0.951** | **0.655** | **0.775** | **0.939** |

Confusion matrix (test):

```
TN=3514  FP=1886
FN=185   TP=3575
```

| Criterion | Result | Status |
|---|---|---|
| Recall ≥ 0.95 | 0.951 | ✅ |
| Precision ≥ 0.85 | 0.655 | ❌ |

**Diagnosis:** Recall met. Insufficient Precision — 1,886 false positives. Best model so far but the ROC-AUC ceiling (~0.94) suggests the problem is in the features, not the algorithm.

#### XGBoost (200 estimators)

| Split | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| Validation | 0.957 | 0.586 | 0.727 | 0.927 |
| **Test** | **0.964** | **0.594** | **0.735** | **0.933** |

Confusion matrix (test):

```
TN=2924  FP=2476
FN=137   TP=3623
```

| Criterion | Result | Status |
|---|---|---|
| Recall ≥ 0.95 | 0.964 | ✅ |
| Precision ≥ 0.85 | 0.594 | ❌ |

**Diagnosis:** Higher Recall (0.964) but lower Precision (0.594) — more FPs than Random Forest. The more aggressive threshold (0.117) generates more false alarms.

#### LightGBM (200 estimators)

| Split | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| Validation | 0.953 | 0.648 | 0.772 | 0.938 |
| **Test** | **0.953** | **0.654** | **0.776** | **0.941** |

Confusion matrix (test):

```
TN=3506  FP=1894
FN=178   TP=3582
```

| Criterion | Result | Status |
|---|---|---|
| Recall ≥ 0.95 | 0.953 | ✅ |
| Precision ≥ 0.85 | 0.654 | ❌ |

**Diagnosis:** Almost identical results to Random Forest. Better ROC-AUC (0.941) but same Precision. Confirms the model ceiling is in the current features.

#### Comparative summary — Phase 3.1

| Model | ROC-AUC | Recall | Precision | FP | FN | Status |
|---|---|---|---|---|---|---|
| Logistic Regression | 0.761 | 1.000 | 0.411 | 5400 | 0 | ❌ predicts everything as attack |
| Random Forest | 0.939 | 0.951 | 0.655 | 1886 | 185 | ❌ Insufficient Precision |
| XGBoost | 0.933 | 0.964 | 0.594 | 2476 | 137 | ❌ Insufficient Precision |
| LightGBM | **0.941** | 0.953 | 0.654 | 1894 | 178 | ❌ Insufficient Precision |

!!! warning "Feature ceiling"
    All models reach ~0.94 ROC-AUC with the current 15 features. The bottleneck is not the algorithm — it is the amount of information available. The `content` features (POST body) are incomplete: `content_has_*` are calculated but not well utilized to differentiate POST attacks from normal traffic.

!!! info "Optimal threshold"
    The threshold was optimized on val searching for Recall ≥ 0.95 with the highest possible Precision. The resulting values (0.15–0.17) are much lower than the default 0.5 — confirming that assuming 0.5 would have given insufficient Recall.

#### Next step — feature improvement

To overcome the Precision ceiling, the options are:

1. **Add content features** — `content_has_*` indicators exist but need analysis of their discriminative power specifically in POST attacks
2. **Feature importance** — identify which features contribute most and if there's untapped signal
3. **Combine method + indicators** — crossed features like `is_post_AND_has_pct27`

---

## Model B — Network Attack Detection

**Dataset:** UNSW-NB15  
**Input:** 49 network flow features  
**Output:** `0` (benign) / `1` (malicious)

### Success criteria

| Metric | Minimum threshold |
|---|---|
| F1 | ≥ 0.88 |
| ROC-AUC | ≥ 0.95 |

### Main features

From the original UNSW-NB15 paper:
`dur`, `proto`, `service`, `state`, `spkts`, `dpkts`, `sbytes`, `dbytes`,
`rate`, `sttl`, `dttl`, `sload`, `dload`, `ct_srv_src`

### Models to evaluate (in order)

1. **Baseline:** Random Forest (known good performance on this dataset)
2. XGBoost
3. LightGBM

### Dataset info (post-EDA)

| Field | Value |
|---|---|
| Train shape | 175,341 × 36 |
| Test shape | 82,332 × 36 |
| Benign train (0) | 56,000 (31.9%) |
| Malicious train (1) | 119,341 (68.1%) |
| Benign test (0) | 37,000 (44.9%) |
| Malicious test (1) | 45,332 (55.1%) |
| Split | Predefined in parquet — do not modify |

### Discarded columns (post-EDA)

| Column | Reason |
|---|---|
| `dwin` | 0.99 correlation with `swin` — redundant |
| `dloss` | 0.98 correlation with `dpkts` — redundant |
| `is_sm_ips_ports` | 0.94 correlation with `sinpkt`, lower correlation with label |
| `attack_cat` | Only for analysis — categorical label of the 9 attack types |

### Preprocessing strategy (post-EDA)

| Aspect | Decision |
|---|---|
| **Nulls** | No imputation — complete dataset, no nulls |
| **Normalization** | `RobustScaler` — extreme outliers in sbytes, sload, dload |
| **proto** (133 values) | Top-10 + `other` category → one-hot |
| **service** (13 values) | Direct one-hot |
| **state** (9 values) | Direct one-hot |
| **`-` in service** | Not null — it is "no service" category, keep it |

### Note on class imbalance

UNSW-NB15 has **more attacks than normal traffic** (68% malicious in train). Initial strategy: `class_weight='balanced'`. If not enough, evaluate SMOTE on training set only. Always adjust threshold post-training.

---

## Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-04-06 | Labels: 0=benign, 1=attack | Consistency between models |
| 2026-04-06 | Offline detection in MVP | Simplifies initial architecture |
| 2026-04-06 | Threshold not fixed at 0.5 | Optimize Recall on attacks |
| 2026-04-06 | Airflow in Phase 4 | Avoid premature complexity |
| 2026-04-06 | No SMOTE in Model A | Mild 59/41 imbalance — class_weight='balanced' sufficient |
| 2026-04-06 | Nulls in content/lenght not imputed | They are NaN by HTTP design in GET requests |
| 2026-04-06 | URL and content-based features | Attacks live in query string (GET) and body (POST) |
| 2026-04-06 | method_is_put is critical feature | 100% of PUT requests are attacks in CSIC 2010 |
| 2026-04-06 | Use URL-encoded chars, not literals | Raw `'` never appears — use `%27`; raw `<` never appears — use `%3C` |
| 2026-04-06 | Discard url_has_union and raw chars | Correlation ~0 or NaN — no discriminative power in URLs |
| 2026-04-06 | 11 columns discarded for being constant | nunique()=1, no info for the model |
| 2026-04-06 | UNSW-NB15: predefined parquet split respected | Dataset has official train/test — don't resplit |
| 2026-04-06 | UNSW-NB15: RobustScaler for numeric features | Extreme outliers in sbytes (max 12M), sload (max 5.9B) |
| 2026-04-06 | UNSW-NB15: proto top-10+other | 133 unique values — direct one-hot would generate too many columns |
| 2026-04-06 | UNSW-NB15: discard dwin, dloss, is_sm_ips_ports | Correlation >0.9 with other features — redundant |
| 2026-04-06 | UNSW-NB15: keep stcpb/dtcpb in initial model | Unexpected -0.255 correlation — validate with post-training feature importance |
| 2026-04-06 | UNSW-NB15: imbalance strategy — class_weight='balanced' first | 68/32 imbalance — try balanced before SMOTE |
| 2026-04-10 | Model A: LR discarded as baseline | ROC-AUC 0.76 — predicts everything as attack, Precision 0.41 |
| 2026-04-10 | Model A: Random Forest meets Recall (0.951) but not Precision (0.655) | Optimal threshold 0.15, 1886 FPs — try XGBoost/LightGBM |
| 2026-04-10 | Model A: optimal threshold 0.15, not 0.5 | Confirms assuming 0.5 would be insufficient for Recall criterion |
| 2026-04-11 | Model A: XGBoost and LightGBM do not beat RF | ROC-AUC ~0.94 in all — feature ceiling, not algorithm |
| 2026-04-11 | Model A: FPs caused by length, not payload | url_length and content_length alone generate noise — need context |
| 2026-04-11 | Model A: url_pct_density and url_param_count improve Precision +0.049 | ROC-AUC 0.939→0.950, Precision 0.655→0.704 — added in preprocess_csic_v2.py |
| 2026-04-11 | Model A: url_has_traversal and post_has_pct27 discarded | NaN — literals never appear, always percent-encoded |
| 2026-04-11 | Model A v2: best LightGBM model ROC-AUC 0.953, Precision 0.702 | Remaining 0.148 gap to reach 0.85 Precision — continue with v3 |
