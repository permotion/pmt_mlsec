# Brief — PMT MLSec

Summary of the project status, key decisions, and learnings. Updated as of 2026-04-13.

---

## What is this

Attack detection system using Machine Learning. MVP with two binary classification models:

| Model | Input | Dataset | Target | Status |
|---|---|---|---|---|
| A — Web Attack Detection | HTTP request features | CSIC 2010 (61,065 req) | Recall ≥ 0.95, Precision ≥ 0.85 | ✅ concluded |
| B — Network Attack Detection | Network flow features | UNSW-NB15 (257K flows) | F1 ≥ 0.88, ROC-AUC ≥ 0.95 | 🔄 in progress |

**Offline** detection in the MVP — no real-time blocking.

---

## Model A — CSIC 2010 (concluded)

### Starting point

The CSIC 2010 dataset has 61,065 HTTP requests from a Spanish store. 59% normal / 41% attacks (SQLi, XSS, buffer overflow, parameter tampering). Attacks always use URL encoding — never literal characters.

Baseline: 4 models (LR, RF, XGBoost, LightGBM) with 15 EDA features. The model easily reached Recall 0.95 but Precision stayed at 0.655 — too many false positives.

### Metrics progression

| Version | ROC-AUC | Recall | Precision | FP | Status |
|---|---|---|---|---|---|
| Baseline | 0.939 | 0.951 | 0.655 | 1886 | ❌ |
| v2 — url_pct_density + url_param_count | 0.950 | 0.950 | 0.704 | 1504 | ❌ |
| v3 — content_pct_density + MLflow | 0.955 | 0.952 | 0.713 | 1444 | ❌ |
| v4 — url_path_depth, url_query_length, url_has_query | 0.966 | 0.949 | 0.803 | 877 | ❌ |
| v5 — Threshold calibration (min_recall_val=0.955) | 0.966 | 0.956 ✅ | 0.792 | 943 | ❌ |
| v6 — content_param_density | 0.966 | 0.955 ✅ | 0.793 | 938 | ❌ |
| v7 — Latin-1 features (not incorporated) | 0.968 | 0.953 ✅ | 0.793 | 936 | ❌ |
| **Target** | — | **0.95** | **0.85** | ~630 | — |

### The 4 problems solved

**Problem 1 — ROC-AUC ceiling of 0.94 (Baseline → v1)**

The LightGBM baseline reached ROC-AUC 0.939 and wasn't improving. The diagnosis was that the limit wasn't the algorithm but the features. Feature importance analysis + analysis of the 1,886 FPs identified that the model lacked information about encoding density in the URL. The `url_pct_density` and `url_param_count` features raised ROC-AUC to 0.950 and Precision to 0.704 (-382 FP).

**Problem 2 — POST body without features (v3 → v4)**

POST attacks had densely encoded bodies but the model only had `content_length`. `content_pct_density` and `content_param_count` were added for the body, followed by URL structure features (`url_path_depth`, `url_query_length`, `url_has_query`) for GET. v4 produced the biggest leap in the project: Precision 0.713 → 0.803 (+0.090), FP -567, and broke the ROC-AUC ceiling for the first time (0.955 → 0.966).

**Problem 3 — Low recall under fixed threshold (v4 → v5)**

With the default threshold (0.5), LightGBM v4 had Recall 0.9492 — below the 0.95 minimum. The 0.5 threshold has no basis in this problem: the model has 41% positives, not 50%. A sweep of `min_recall_val` (0.950 → 0.985) was implemented to optimize the threshold in validation, seeking the one that maximizes Precision while maintaining Recall ≥ target. The optimal value was `min_recall_val=0.955` → calibrated threshold 0.2573 → Test Recall 0.9556 ✅.

**Problem 4 — Root cause of FPs: encoding confusion (v6)**

With 938 FPs after v5, the raw CSV was inspected. High-confidence FPs (proba > 0.70) were all legitimate Spanish store forms with names like `Murgu%EDa`, `lIMpi%24a%FA%F1as`. The model confused them with attacks because `content_pct_density` counts all `%XX` equally — `%F1` (n-tilde) produces the same signal as `%27` (SQLi). The `cookie` and `content-type` headers were discarded as signals: 100% of requests have a cookie and content-type is identical between FP and TN of the same method.

### The problem that couldn't be solved

**The Latin-1 hypothesis failed (v7)**

The hypothesis was: attacks never use Latin-1 (there is no reason to encode n-tilde in an SQL payload), so `content_pct_latin1_density` would discriminate FP from TN. The hypothesis was technically correct for real attacks — but CSIC 2010 has a quirk: the attack generator builds requests against a Spanish store and includes Spanish field names with accented characters. The body of a typical POST attack is `apellidos=Garc%EDa&pass=%27+OR+1%3D1--` — the injection payload is in the `pass` value, but the `apellidos` field name has `%ED` (i-acute). Distribution is virtually identical: normal mean 0.00420 vs attack 0.00413. POST correlation: -0.004. Impact: -2 FP.

### Practical ceiling and decision

After v5, v6, and v7, the pattern is clear: the 936 FPs are normal requests that the model cannot differentiate from attacks using the available dimensions of individual HTTP fields.

| Dimension analyzed | Result |
|---|---|
| URL/body length and structure | Exhausted since v4 |
| Keyword indicators (`%27`, `SELECT`) | 98.6% of FPs have none |
| Query string structure | Exhausted since v4 |
| Parameter density (`content_param_density`) | Real but marginal signal (-5 FP) |
| Latin-1 encoding | No separation — attacks also have Latin-1 |
| HTTP Headers (cookie, content-type) | No signal — constant in the dataset |

**Decision:** accept Precision ~0.793 as the practical ceiling and advance to Model B. The 0.057 gap to reach 0.85 would require semantic parsing of parameter values (distinguishing `key=normal_value` from `key=%27OR1%3D1`) or session features — a change in approach, not more feature engineering on HTTP fields.

Precision 0.793 with Recall 0.953 is a valid starting point for production with manual review of alarms. With 936 FPs, the false alarm rate is manageable in an offline detection system.

### Code status

```
src/mlsec/data/
├── preprocess_csic_v1.py   → features.parquet      (15 features)
├── preprocess_csic_v2.py   → features_v2.parquet   (17 features)
├── preprocess_csic_v3.py   → features_v3.parquet   (22 features)
└── preprocess_csic_v4.py   → features_v4.parquet   (23 features) ← final version

notebooks/experiments/
├── csic2010_feature_analysis_v1.ipynb  ← baseline FP analysis
├── csic2010_feature_analysis_v2.ipynb  ← url features
├── csic2010_feature_analysis_v3.ipynb  ← content POST + MLflow
├── csic2010_feature_analysis_v4.ipynb  ← url structure GET
├── csic2010_feature_analysis_v5.ipynb  ← threshold calibration
├── csic2010_feature_analysis_v6.ipynb  ← content_param_density
├── csic2010_fp_analysis_v6.py          ← raw CSV analysis → root cause
└── csic2010_feature_analysis_v7.ipynb  ← Latin-1 hypothesis (unconfirmed)
```

**MLflow:** `mlsec-model-a` experiment, `mlflow.db` SQLite backend. 28 runs, naming `model-a-{algorithm}-features-{version}`.

---

## Model B — UNSW-NB15 (in progress)

### Dataset

UNSW-NB15: 257,673 network flows (175,341 train / 82,332 test — predefined splits). 9 attack categories: Generic (33%), Exploits (28%), Fuzzers (15%), DoS (4%), Reconnaissance (5%), Analysis, Backdoor, Shellcode, Worms. Inverse imbalance: 68% attacks in train.

### EDA Findings

- `dload` (bytes downloaded): -0.394 correlation with the label — normal traffic downloads more data
- `rate`, `ct_dst_sport_ltm`: 0.338 / 0.357 correlation
- Extreme outliers: `sbytes` max 12M, `sload` max 5.9B → `RobustScaler`
- Discarded redundant features: `dwin` (0.99 with `swin`), `dloss` (0.98 with `dpkts`), `is_sm_ips_ports`
- `proto`: 133 unique values → top-10 + "other" encoding
- No null values

### Preprocessing strategy

- `RobustScaler` for continuous numerical features (extreme outliers)
- Top-10+other for `proto`, direct one-hot for `service` and `state`
- Predefined splits in the parquets — no custom train/test split

### What's next

1. Implement `preprocess_unsw.py` with EDA decisions
2. Generate `features.parquet` (train + test)
3. Train baseline (RF, XGBoost, LightGBM) — no LR, doesn't scale well to 62 continuous features
4. Analyze FP/FN with the same workflow as Model A
5. Iterate features until F1 ≥ 0.88 / ROC-AUC ≥ 0.95

### Differences from Model A

| Aspect | Model A (CSIC) | Model B (UNSW) |
|---|---|---|
| Input features | Text (URL, body) → manual engineering | Network numerical → less manual engineering |
| Target metric | Recall + Precision | F1 + ROC-AUC |
| Imbalance | Mild 59/41 | Inverse 32/68 (more attacks than normal) |
| Splits | Generated by us (70/15/15) | Predefined in dataset |
| Threshold | Calibrated with min_recall_val sweep | To be defined |

---

## Key learnings of the project

**1. The default threshold (0.5) is almost always wrong.**
In Model A, with 41% positives, the optimal threshold was 0.2573. Fixing the threshold in validation seeking a minimum recall target is much more robust than looking for the maximum F1 point.

**2. Analyzing FPs in the raw CSV is worth more than adding features blindly.**
The root cause of the FPs (Latin-1 vs attack encoding confusion) was only visible by reading the actual requests. Correlation and feature importance analysis only say "feature X has signal" — it doesn't say why the model fails in specific cases.

**3. Correlations in the relevant subpopulation, not in the entire dataset.**
`content_param_density` has a global correlation of +0.066 (noise) but a POST correlation of -0.216 (real signal). Calculating correlations on the full dataset for body features diluted the signal with GETs that have empty bodies.

**4. Synthetic datasets have quirks that break reasonable hypotheses.**
CSIC 2010 was generated with a script that includes Spanish field names in the attacks. This made the Latin-1 hypothesis — correct in theory — fail empirically. Benchmark datasets have limitations that are only discovered when inspecting the raw data.

**5. Identifying the practical ceiling is a result, not a failure.**
Knowing that Precision ~0.793 is the limit of the individual HTTP fields approach is valuable information — it prevents wasting iterations on features that won't move the needle.
