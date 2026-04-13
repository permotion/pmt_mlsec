# PMT MLSec

ML-based security attack detection system. Two binary classifiers built on public benchmark datasets, with MLflow experiment tracking and offline detection.

**Documentation:** https://permotion.github.io/pmt_mlsec/

---

## Models

| Model | Input | Dataset | Target |
|---|---|---|---|
| A — Web Attack Detection | HTTP request features | CSIC 2010 (61K requests) | Recall ≥ 0.95, Precision ≥ 0.85 |
| B — Network Attack Detection | Network flow features | UNSW-NB15 (257K flows) | F1 ≥ 0.88, ROC-AUC ≥ 0.95 |

---

## Model A — CSIC 2010 (concluded)

7 iterations of feature engineering on HTTP request data (SQLi, XSS, buffer overflow, parameter tampering detection).

### Results

| Version | ROC-AUC | Recall | Precision | FP |
|---|---|---|---|---|
| Baseline | 0.939 | 0.951 | 0.655 | 1886 |
| v2 — url_pct_density + url_param_count | 0.950 | 0.950 | 0.704 | 1504 |
| v3 — content_pct_density + MLflow | 0.955 | 0.952 | 0.713 | 1444 |
| v4 — url_path_depth, url_query_length, url_has_query | 0.966 | 0.949 | 0.803 | 877 |
| v5 — threshold calibration (min_recall_val=0.955) | 0.966 | 0.956 ✅ | 0.792 | 943 |
| v6 — content_param_density | 0.966 | 0.955 ✅ | 0.793 | 938 |
| v7 — Latin-1 encoding features | 0.968 | 0.953 ✅ | 0.793 | 936 |
| **Target** | — | **0.95** | **0.85** | ~630 |

**Best model:** LightGBM — Recall 0.953 ✅ / Precision 0.793 / ROC-AUC 0.968

**Decision:** Precision ~0.793 accepted as the practical ceiling of the HTTP field feature approach. The 936 remaining FPs are structurally ambiguous — the model confuses Latin-1 encoded Spanish characters (`%F1`=ñ, `%ED`=í) with attack encoding (`%27`=`'`, `%3C`=`<`) because `content_pct_density` counts all `%XX` sequences equally. Closing the gap requires semantic parsing of parameter values or session-level features — a different approach.

### Key findings

- **PUT = 100% attacks** — strongest single feature in the dataset
- **Threshold 0.5 is wrong** — with 41% positives the optimal threshold was 0.2573; calibrated via `min_recall_val` sweep on validation set
- **Subpopulation analysis matters** — `content_param_density` has global correlation +0.066 (noise) but POST-only correlation -0.216 (real signal)
- **CSIC 2010 dataset quirk** — the attack generator builds requests against a Spanish e-commerce site and includes Spanish field names in attack requests, so both normal and attack traffic have similar Latin-1 encoding rates — this broke an otherwise reasonable hypothesis

---

## Model B — UNSW-NB15 (in progress)

EDA complete. Preprocessing and training pending.

**EDA findings:**
- 9 attack categories: Generic (33%), Exploits (28%), Fuzzers (15%), DoS (4%), Reconnaissance (5%), and others
- Inverse class imbalance: 68% attacks in train set
- Strongest correlations: `dload` (-0.394), `ct_dst_sport_ltm` (0.357), `rate` (0.338)
- Extreme outliers (`sbytes` max 12M, `sload` max 5.9B) → RobustScaler
- Redundant features removed: `dwin`, `dloss`, `is_sm_ips_ports`

---

## Stack

- **Python 3.11** — scikit-learn, LightGBM, XGBoost, pandas, numpy
- **MLflow** — experiment tracking (SQLite backend, experiment `mlsec-model-a`, 28 runs)
- **MkDocs Material** — full project documentation
- **GitHub Actions** — automatic docs deployment to GitHub Pages

## Structure

```
src/mlsec/data/          ← preprocessing scripts (v1–v4 for CSIC)
notebooks/experiments/   ← feature engineering notebooks (v1–v7)
notebooks/eda/           ← exploratory analysis
docs/                    ← MkDocs documentation
```
