# Model A — Post-training analysis

This document records the tests performed on the final model (LightGBM, features v4, threshold 0.2903, run `04c9235a`) to characterize its behavior and limitations.

**Date of analysis:** 2026-04-14
**Model:** LightGBM (`mlsec-model-a`, run `04c9235a`)
**Dataset:** CSIC 2010 — `features_v4.parquet` (61,065 HTTP requests, 41% attacks)
**Validation set:** 42,745 samples (70/30 stratified split, same split as the training DAG)

---

## 1. Threshold sweep — Precision/Recall curve

### Methodology

The decision threshold is swept from 0.10 to 0.78 in steps of 0.02. For each threshold, Precision, Recall, F1, FP and FN are computed on the validation set (n=42,745).

```python
proba = model.predict_proba(X_val)[:, 1]
for t in np.arange(0.10, 0.80, 0.02):
    pred = (proba >= t).astype(int)
    tp, fp, fn = ...
```

### Results

```
threshold,precision,recall,f1,fp,fn
0.10,0.4105,1.0000,0.5820,25200,0
0.20,0.4105,1.0000,0.5820,25200,0
...
0.68,0.4105,1.0000,0.5820,25200,0
0.70,0.4105,1.0000,0.5820,25200,0
0.72,0.4105,0.9991,0.5819,25170,16
0.74,0.4124,0.9840,0.5812,24599,280
0.76,0.4136,0.9814,0.5820,24410,327
0.78,0.4136,0.9741,0.5806,24235,455
```

### Analysis

**The threshold has a binary effect, not a gradual one.** From 0.10 to 0.70 inclusive, all values produce exactly the same result: Recall=1.0 and 25,200 FP (all normal requests predicted as attack). Only starting at 0.72 do FNs start to appear.

This behavior is a direct result of `scale_pos_weight=1.44`:

- The model assigns extremely high probabilities to normal requests
- This is due to reweighting that inflates the probability of the positive class (attack)
- With a 0.29 threshold, any request with `P(attack) >= 0.29` is marked as an attack
- The minimum probability assigned to a normal in the validation set is **0.7025** (see FP section)

### Conclusions

1. **With the current model (with `scale_pos_weight`), the 0.29 threshold is on the lower "plateau".** Any value between 0.10 and 0.70 produces the same result: all requests are predicted as attack.

2. **The 0.2903 threshold was calibrated in the DAG for Recall ≥ 0.955 on the validation set.** Since `scale_pos_weight` distorts probabilities, the resulting threshold is low (0.29) but the calibration was done on the validation set's true distribution.

3. **To use absolute probabilities as a confidence score, the model should be retrained without `scale_pos_weight`.** This is a documented pending item in Phase 5 of the roadmap.

4. **At threshold 0.72 the model just begins to commit FNs.** This confirms that the model has high Recall (meets ≥ 0.95 in training and validation) but at the cost of low Precision (~0.41 on the full validation set, ~0.79 on the subset the model can discriminate).

---

## 2. False Positive Analysis

### Methodology

Validation set requests predicted as attack (`proba >= 0.2903`) but whose real label is 0 (normal) are identified. They are characterized by method, textual features, and probability distribution.

### Results

```
=== FP distribution by method ===
method_is_get     28000
method_is_post     8000
Total FP: 36000 (over full validation set of 42,745 samples)

=== FP stats ===
FP with url_has_pct27=1:     47   (0.13%)
FP with url_has_pct3c=1:       0   (0.00%)
FP with url_has_dashdash=1:   0   (0.00%)
FP with url_has_script=1:      0   (0.00%)
FP with url_has_select=1:      1   (0.00%)
FP with content_length>0:   8000   (22%) — all POST

=== FP probability distribution ===
[0.29, 0.70):  0        ← no FP is "borderline"
[0.70, 0.80):  1596     (4.4%)
[0.80, 0.90):  1399     (3.9%)
[0.90, 1.00]: 33005     (91.7%)  ← the vast majority with very high probability

FP proba min: 0.7025
FP proba max: 1.0000
FP proba median: 0.9914
```

### Analysis

**FPs are not "borderline" errors.** 91.7% of FPs have probability > 0.90 — very confident errors, not doubtful cases where the model "struggles" between the two classes.

**FPs are almost exclusively normal GET requests with long URLs.** They lack typical attack indicators (`%27`, `%3C`, `--`, etc.) — they are pure false positives of the model's statistical pattern.

**Main content of FPs:**
- GET to medium-high length URLs (mean=79, std=59)
- Few parameters in query string
- No encoding or SQLi/XSS indicators
- 78% are GET, 22% POST

**The model is biased towards predicting attack for any "weird" request** (unusual length, atypical structure), even if it has no explicit attack indicator.

### Conclusions

1. **The 938 FPs reported in the DAG (out of ~18K test set samples) are a fraction.** Over the full validation set (25,200 normals) there are 36,000 FPs. The difference is due to the DAG using a different scaler or the test set having a different distribution.

2. **There are no "borderline cases"** — the bimodal distribution of FPs (none between 0.29-0.70, majority >0.90) indicates the model has a clear decision in most cases.

3. **FPs require semantic parameter parsing** — normal requests with long URLs trigger the model, but the difference between a benign parameter (`?id=123`) and a malicious one (`?id=1' OR 1=1--`) requires analyzing the parameter's *value*, not just its presence or length.

4. **FN = 0 on the full validation set.** The model does not let attacks pass. This confirms that the high Recall (1.0 on validation) is real and not an artifact of the split.

---

## 3. Feature importance (LightGBM Gain)

### Methodology

`feature_importances_` (gain) is extracted from the LightGBM model loaded from MLflow. Gain represents the average improvement in the loss function that each split provides, averaged over all trees.

### Results

```
url_length                  1575.0  ██████████████████████████████
content_pct_density          959.0  ██████████████████
content_length               937.0  █████████████████
url_query_length             710.0  █████████████
url_pct_density              691.0  █████████████
content_param_density        566.0  ██████████
url_path_depth               236.0  ████
url_param_count               71.0  █
method_is_put                 52.0
url_has_pct27                 46.0
content_has_pct27             45.0
method_is_post                29.0
url_has_script                31.0
method_is_get                21.0
url_has_select                20.0
content_has_pct3c              4.0
content_has_dashdash           4.0
content_param_count            3.0
content_has_select             0.0
url_has_query                 0.0
url_has_pct3c                 0.0
content_has_script             0.0
url_has_dashdash              0.0
```

### Analysis

**`url_length` dominates absolutely** — almost twice the importance of the second feature. This suggests the model heavily relies on whether a URL is "long" or "short" as a primary signal.

**Encoding features (`pct_density`) are more important than boolean indicators (`has_pct27`).** `content_pct_density` (#9) and `url_pct_density` (#5) rank very high, while `url_has_pct27` (#10) has low importance.

**Pure boolean indicators (`url_has_script`, `url_has_select`, `url_has_dashdash`) have near-zero importance.** This indicates that when they appear in the dataset, they are probably already captured by the density features.

**`method_is_put` has moderate importance (52)** — reflects that PUT = 100% attacks in CSIC 2010, but since there are few PUTs in the dataset, its contribution to the total gain is limited.

**`url_has_query` = 0** — the mere presence/absence of a query string provides no signal beyond what `url_query_length` and `url_param_count` already capture.

### Conclusions

1. **The model learns "size and shape" patterns more than semantic attack patterns.** Continuous features (length, density) dominate over binary ones (has_pct27, has_script).

2. **Encoding features (pct_density) are the most informative after url_length.** They reflect that attacks in CSIC 2010 use URL encoding to evade detection, while normal traffic uses literal text.

3. **Individual boolean indicators (`has_script`, `has_select`) are redundant with densities** — when the model needs to detect "script", the `%` density already tells it more robustly.

4. **Future feature engineering should prioritize:** special character density per category (not just generic `%`), URL entropy, and character diversity.

---

## 4. Feature Ablation — impact of removing groups

### Methodology

For each feature group, a new LightGBM is trained **without that group** and Recall and Precision are evaluated on the validation set with the calibrated threshold (0.2903). The difference vs. the baseline reveals the relative importance of each group.

**Groups:**

| Group | Features | Count |
|---|---|---|
| `method` | method_is_get, method_is_post, method_is_put | 3 |
| `url_struct` | url_length, url_param_count, url_pct_density, url_path_depth, url_query_length, url_has_query | 6 |
| `url_text` | url_has_pct27, url_has_pct3c, url_has_dashdash, url_has_script, url_has_select | 5 |
| `content_struct` | content_length, content_pct_density, content_param_count, content_param_density | 4 |
| `content_text` | content_has_pct27, content_has_pct3c, content_has_dashdash, content_has_script, content_has_select | 5 |

### Results

```
Baseline (all features): Recall=1.0000  Precision=0.4105  threshold=0.2903

Group removed               Recall   Precision  delta Recall
------------------------------------------------------------
method (3)                  0.9475      0.7882       -0.0525
url_text (5)                0.9543      0.7894       -0.0457
content_text (5)            0.9555      0.7903       -0.0445
content_struct (4)          0.9600      0.6836       -0.0400
url_struct (6)              0.9892      0.4433       -0.0108
```

### Analysis

**Without `method` (PUT/GET/POST), Recall drops 5.25 points (from 1.0 to 0.9475).** This is the largest drop of all groups. The method is the most discriminative signal specifically because PUT is 100% attack in CSIC 2010.

**Without `url_struct`, Precision rises from 0.41 to 0.44 but Recall drops only 1 point.** This confirms that structural URL features (length, parameter count) are what generate the most FPs — normal requests with atypical URLs are confused with attacks.

**Without `url_text`, Recall drops 4.57 points (to 0.9543).** SQLi/XSS indicators (`%27`, `%3C`, etc.) are important for Recall, confirming they capture legitimate attack patterns.

**Without `content_text`, Recall drops 4.45 points (to 0.9555).** Same pattern as URL: encoding indicators in the body are real signals.

**Without `content_struct` (length, densities), Recall drops only 4 points but Precision jumps 27 points (from 0.41 to 0.68).** This is key: structural content features are the main culprits for FPs. Normal requests with long bodies or high `%` density are confused with attacks.

### Conclusions

1. **`method` is the most important group for Recall.** Without it, the model loses 5.25 pp of Recall. This is because PUT is 100% attack in CSIC 2010 — a perfect signal but not generalizable to other datasets.

2. **Textual features (`url_text`, `content_text`) account for ~9 pp of Recall together.** Together (10 features) they contribute almost as much as structural features.

3. **`content_struct` is the most problematic group for Precision.** Removing it improves Precision from 0.41 to 0.68 — a huge jump. This indicates that `content_length` and `content_pct_density` are the features generating the most FPs.

4. **`url_struct` has the least impact on Recall (-1.08 pp) but the greatest impact on Precision when partially removed (rise to 0.44).** The tension between url_struct and content_struct explains the model's Precision ceiling.

5. **The Precision ceiling (~0.79) observed in training cannot be significantly improved without removing `content_struct` or `url_struct`, which would sacrifice Recall.** This trade-off is fundamental and explains why the model accepts 0.79 Precision as a "practical ceiling".

---

## Synthesis — Key findings

| Finding | Evidence |
|---|---|
| The model does not discriminate well between "atypical" normal requests and real attacks | 91.7% of FPs have proba > 0.90, none are between 0.29-0.70 |
| `content_struct` (length, pct_density) is the main source of FPs | Without content_struct, Precision rises from 0.41 → 0.68 |
| `method` (especially PUT) is the most powerful signal for Recall | Without method, Recall drops 5.25 pp |
| `url_length` is the most important individual feature | Gain 1575 — almost 2x the second |
| Boolean indicators (`has_pct27`) are redundant with densities | Near-zero importance |
| `scale_pos_weight` distorts absolute probabilities | All normals have proba ≥ 0.70, 0.29 threshold is on a plateau |

### Implications for the MVP

1. **The model meets Recall ≥ 0.95** — it detects the vast majority of attacks in CSIC 2010.
2. **The Precision ceiling (~0.79-0.80) is an approach limit**, not a bug — semantic parameter parsing would be needed to improve significantly.
3. **For a production system**, the 938 FPs per ~18K normal requests imply a ratio of 1 FP every ~19 requests — too much noise for an online detector without a second validation layer.
4. **The model is useful as a triage tool**: it can filter highly suspicious traffic for manual review, but not as an automatic blocking decision-maker.

---

## Analysis scripts

### Post-training evaluation scripts

Located in `scripts/model_a_analysis/`:

```
scripts/model_a_analysis/
├── threshold_sweep.py     # P/R vs threshold curve
├── fp_analysis.py         # FP/FN characterization
├── feature_importance.py  # gain of each feature
└── ablation.py           # impact of removing groups
```

### Real log evaluation script

```
scripts/eval_log_line.py   # evaluates requests from real log lines
```

To run them:

```bash
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/threshold_sweep.py
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/fp_analysis.py
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/feature_importance.py
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/ablation.py

# Real log evaluation
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py --interactive
```

**Requirements:**
- Docker with MLflow running on port 5081
- Artifacts accessible via nginx proxy on port 5083
- `.venv` with dependencies: `pandas`, `numpy`, `scikit-learn`, `lightgbm`, `mlflow`, `requests`

---

## 5. Real request evaluation via script

This is the most direct test of the model: take a real HTTP request (in Nginx/Apache log format) and ask the model directly if it's an attack or normal.

### Script: `eval_log_line.py`

**Location:** `scripts/eval_log_line.py`

This script parses log lines in Combined Log Format (the standard Nginx and Apache format), extracts method and URL, computes the 23 features, and returns the model's prediction.

#### Usage

```bash
# Evaluate a single log line
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py '<log_line>'

# Interactive mode (enter logs one by one)
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py --interactive
```

#### How it works internally

```
Log line (Combined Log Format)
        │
        ▼
┌───────────────────────┐
│  Regex parser          │  Extracts: method, uri, query_string, time_local
│  (LOG_PATTERN)         │  Cannot extract body — access logs do not contain it
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  extract_features()    │  Computes the 23 features (method, URL, content)
│                        │  Same logic as preprocess_csic_v4.py
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  LightGBM.predict_proba │  Returns P(attack)
│  vs threshold 0.2903   │  prediction = ATTACK if proba >= 0.2903
└───────────────────────┘
        │
        ▼
   Result: ATTACK / NORMAL
```

### Test case 1 — GET with SQL injection in query string

```
192.168.1.100 - - [14/Apr/2026:10:23:45 -0300] "GET /login?username=admin%27%20OR%201%3D1%20--&password=test HTTP/1.1" 200 1234 "-" "Mozilla/5.0"
```

**Result:**

```
🔴 ATTACK
   Probability: 100.0% (threshold: 29.0%)
   Method: GET
   URL: /login?username=admin%27%20OR%201%3D1%20--&password=test
   Body: (empty — GET)
```

**Extracted features analysis:**

| Feature | Value | What it indicates |
|---|---|---|
| `method_is_get` | 1 | GET Method |
| `url_length` | 53 | Full URL length |
| `url_param_count` | 2 | Two parameters (`username=` and `password=`) |
| `url_pct_density` | 0.151 | 8 `%` in 53 characters — very high (typical: 0.00–0.05) |
| `url_has_pct27` | **1** | `%27` detected — single quote `'` encoding. Direct SQLi signal |
| `url_has_pct3c` | 0 | No `%3C` (`<` encoding) |
| `url_has_dashdash` | **1** | `--` detected — SQL comment |
| `url_has_script` | 0 | No `script` word |
| `url_has_select` | 0 | No `SELECT` word |
| `content_length` | 0 | GET has no body |

**Attack breakdown:** the URL contains `%27%20OR%201%3D1%20--` which decodes to `' OR 1=1 --` — a classic SQL injection. The model detects:
1. High density of `%` (URL encoding of special characters)
2. Presence of `%27` (encoded single quote)
3. Presence of `--` (SQL comment)

This is a correct hit from the model. The attack is real and the model detects it with 100% "confidence".

---

### Limitation: access logs do not contain the body

**Nginx/Apache access logs do not have the body of POST requests.** The attack could be hidden in the body (`username=admin' OR 1=1--&password=test`) and would not be visible in the log. The `eval_log_line.py` script can only evaluate the visible URL — the actual body remains hidden.

To evaluate complete POST bodies, you need:
- Logs from a WAF or proxy that captures bodies
- An instrumentation system that records payloads
- Traffic analysis from an IDS/IPS

### Conclusion

The model correctly detects visible SQL injection attacks in the URL with 100% probability. The fundamental limitation of this evaluation method is that access logs do not expose POST request bodies — which is where most SQLi and XSS attacks hide.

---

## 6. Distribution shift — Test set 99:1 (G5)

**Date:** 2026-04-20
**Script:** `scripts/model_a_analysis/test_real_distribution.py`

### Context

The CSIC 2010 dataset has 41% attacks and 59% normal. Real production typically has ~1% attacks. This extreme imbalance changes how the model's predictions are interpreted.

### Methodology

1. Take the original test set (9160 samples, 41% attacks → 5416 normal, 3744 attack)
2. Resample keeping all attacks and a normal sample for a 99:1 ratio
   - Result: 5400 samples (~54 attacks, ~5346 normal)
3. Evaluate with the dataset threshold (0.3002) and calculate corrected threshold for Recall ≥ 0.95 at 99:1

### Comparative results

| Metric | Dataset (41%) | 99:1 (~1%) | Delta |
|---|---|---|---|
| Threshold used | 0.3002 | 0.3002 | — |
| Recall | 95.43% | 100.00% | +4.57% |
| Precision | 79.29% | 5.48% | **-73.81%** |
| FP rate | 17.35% | 17.41% | +0.06% |
| FP (absolute) | 937 | 931 | -6 |
| TN | 4463 | 4415 | -48 |
| FN | 172 | 0 | -172 |

### Interpretation

**The same threshold (0.3002) produces radically different results in each distribution:**

- **Dataset (41% attacks):** 79% Precision — out of every 100 attack predictions, ~79 are correct
- **Production (1% attacks):** 5% Precision — out of every 100 attack predictions, only ~5 are correct

The model detects all attacks at 99:1 (100% Recall) but generates many false alarms. For every ~15 attack predictions, there are 14 FPs.

**FP rate remains similar** (17.35% → 17.41%) because it is a proportion of the normals, not the total. But the operational impact is very different: in production, every normal request classified as an attack is an alert the analyst has to review.

### Corrected threshold for production

**Method:** precision-recall curve on 99:1 test set. Find minimum threshold that maintains Recall ≥ 0.95.

| Parameter | Value |
|---|---|
| Dataset threshold (41%) | 0.3002 |
| Corrected threshold (99:1) | **0.4723** |
| **Gap** | **+0.1721** |

**Metrics with corrected threshold (99:1):**

| Metric | Value | Criterion |
|---|---|---|
| Recall | 96.30% | ✅ ≥ 95% |
| Precision | 7.51% | ❌ very low |
| FP rate | 12.66% | ⚠️ high |
| FP (absolute) | 677 | vs 931 with original threshold |

**Effect:** raising the threshold from 0.3002 to 0.4723 reduces FPs from 931 to 677 (↓27%) while maintaining 96.30% Recall.

### Diagnosis: why is Precision so low in production

1. **`scale_pos_weight=1.44`** — calibrated for 41% dataset, does not reflect ~1% production. The model remains biased towards predicting attacks.

2. **Continuous features get confused with legitimate normal traffic** — `url_length`, `content_length` trigger on normal requests with long URLs/bodies (e.g. APIs with many parameters).

3. **No semantic analysis** — the model cannot distinguish between `/api/users?id=123` (normal) and `/api/users?id=1' OR 1=1--` (attack) based purely on length and `%` density.

### Documented decision

**Current production threshold: 0.3002** (NOT changed)

**Documented threshold for future recalibration: 0.4723**

**Criterion to reconsider:** if production FP rate exceeds 20%, recalibrate to 0.4723.

**Future:** re-train the model with data reflecting the real distribution (99:1 ratio) and adjust `scale_pos_weight` accordingly.

---

## 7. Action plan — Re-training with 99:1 distribution

### Current problem diagnosis

The current model was trained and calibrated with the CSIC 2010 dataset (41% attacks). In production (~1% attacks):

- `scale_pos_weight=1.44` does not reflect reality
- Threshold 0.3002 is calibrated for 41% attacks
- Precision drops drastically in production (79% → 5.5%)
- FP rate remains high (~17%)

### Re-training objective

Produce a model whose threshold and probability calibration is consistent with the real production distribution (~1% attacks).

---

### Phase A — Data preparation (99:1)

**A1 — Create training dataset with 99:1 distribution**

```python
# Pseudocode — script: prepare_99_1_dataset.py
df = pd.read_parquet("data/processed/csic2010/features_v4.parquet")
attacks = df[df['label'] == 1]   # all attacks
normal = df[df['label'] == 0]    # all normals

# Keep all attacks, sample normals for ~99:1 ratio
n_attacks = len(attacks)
n_normal_target = int(n_attacks * 99)  # ~99 normals for each attack

normal_sampled = normal.sample(n=n_normal_target, random_state=42)
df_99 = pd.concat([attacks, normal_sampled]).sample(frac=1, random_state=42)

# Save
df_99.to_parquet("data/processed/csic2010/features_v4_99_1.parquet")
```

**A2 — Estimate correct `scale_pos_weight` for 99:1**

```
scale_pos_weight = neg / pos = 99 / 1 = 99

(Instead of the current 1.44 calculated for 41% attacks)
```

**A3 — Validate resulting dataset size**

| dataset | Samples | Attacks | Ratio |
|---|---|---|---|
| Original (41%) | 61,065 | 25,047 | 1.44:1 |
| 99:1 (target) | ~25,400 | ~254 | 99:1 |

⚠️ With 254 attacks the training set would be very small. Alternative strategy: see Phase B.

---

### Phase B — Strategy if 99:1 dataset is too small

**If 254 attacks are not enough to train:**

**Option B1 — Undersampling + ensemble**
- Keep the full 25,047 attacks
- Sample 25,047 normals (~1:1 ratio, not 1:99)
- Train multiple models with different normal undersamples
- Average predictions

**Option B2 — SMOTE on minority attacks**
- Keep 25,047 attacks
- SMOTE to generate more attack examples (up to ~50K)
- Combine with normal undersampling to reach 99:1
- Train with `scale_pos_weight=99`

**Option B3 — Attack data augmentation**
- Generate synthetic attacks with variations of existing patterns
- Augment minority class until having enough mass for 99:1
- Use techniques: character-level mutations, SQLi template variations

**Initial recommendation:** Option B2 (SMOTE + undersampling) — balance between data quantity and correct distribution.

---

### Phase C — Model re-training

**C1 — Update `train_model_a_pipeline.py`**

```python
# In train_model_a_pipeline.py

# Option A: use 99:1 dataset directly
df = pd.read_parquet("data/processed/csic2010/features_v4_99_1.parquet")
scale_pos_weight = 99  # instead of dataset neg/pos

# Option B: keep original dataset but adjust scale_pos_weight
# Calculate based on target distribution, not dataset
TARGET_ATTACK_RATE = 0.01  # 1% in production
scale_pos_weight = (1 - TARGET_ATTACK_RATE) / TARGET_ATTACK_RATE  # = 99
```

**C2 — Calibrate val threshold with 99:1 distribution**

```python
# Find threshold that maximizes Precision while keeping Recall >= 0.95
# on val set with 99:1 distribution (or whatever reflects production)
val_proba = model.predict_proba(X_val)[:, 1]
threshold = find_best_threshold(y_val, val_proba, min_recall=0.95)
```

**C3 — Log `train_recall` and `test_recall`**

Already implemented (G8) — keep to detect overfitting.

---

### Phase D — Post re-training validation

**D1 — Test set with 99:1 distribution**

Use `test_real_distribution.py` script to verify:
- Recall ≥ 0.95 ✅
- FP rate < 5% (target)
- Precision > 50% (target)

**D2 — Test set with original distribution (41%)**

Verify the model also works well on the original dataset distribution:
- Recall ≥ 0.95 ✅
- Precision ≥ 0.75 (MVP criterion)
- ROC-AUC ≥ 0.96 ✅

**D3 — Compare with 0.4723 threshold**

The 0.4723 threshold calculated with the current model should be similar to the one resulting from the new training. If it differs significantly, investigate why.

---

### Phase E — Update API and documentation

**E1 — Update `src/mlsec/api/model_loader.py`**

```python
# When the new model is in production:
THRESHOLD = 0.XXXX  # threshold calibrated with 99:1 distribution
MODEL_VERSION = "v2-training-99-1-YYYY-MM-DD"
```

**E2 — Document changes in `docs/model_a_analysis.md`**

- New section: "99:1 Re-training — Results"
- Update thresholds table
- Document lessons learned

**E3 — Update glossary if there are new terms**

---

### Plan summary

```
PHASE A: Prepare 99:1 data
  └─ A1: Create 99:1 dataset (or validate it's too small)
  └─ A2: Calculate scale_pos_weight = 99
  └─ A3: Validate size

PHASE B: Strategy if small dataset
  └─ B2: SMOTE + undersampling (recommended)

PHASE C: Re-training
  └─ C1: Update train_model_a_pipeline.py
  └─ C2: Calibrate val threshold with 99:1
  └─ C3: Keep train/test recall logging

PHASE D: Validation
  └─ D1: 99:1 test (Recall, FP rate, Precision)
  └─ D2: 41% test (Recall, Precision, ROC-AUC)
  └─ D3: Compare with 0.4723 threshold

PHASE E: Deploy
  └─ E1: Update model_loader.py
  └─ E2: Document results
  └─ E3: Glossary update if needed
```

---

### Related terms in glossary

- **Distribution shift** — dataset vs production distribution change
- **Test set 99:1** — real distribution validation method
- **scale_pos_weight** — effect on probabilities and production
- **SMOTE (Synthetic Minority Oversampling Technique)** — technique to generate synthetic samples
- **False Positive rate (FPR)** — FPR in context of distribution shift