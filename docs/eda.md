# EDA (Exploratory Data Analysis)

## What it is and its role

EDA is the **initial investigation of the data** — it is done before building any pipeline. Its goal is to understand the dataset's structure, detect quality issues, and decide which features to build for the model.

```
[Ingestion]  →  [EDA]  →  [Preprocessing]  →  [Training]  →  [Experiments]  →  [Registry]
                ↑               ↑                                  ↑
         data exploration   implementation                     iteration over
         without model      of EDA decisions                   trained model
                                                               with results
```

**EDA Outputs:**

1. **Knowledge** — which columns to use, where attacks live, how to handle nulls
2. **Preprocessing decisions** — what to normalize, how to encode categoricals, imbalance strategy
3. **Candidate features** — variables that the model will receive as input

When the notebook matures, transformations become scripts with `/refactor-notebook`.

### EDA vs Preprocessing vs Experiment

| | EDA | Preprocessing | Experiment |
|---|---|---|---|
| **Question** | What's in the data? | How do I transform the data? | Why does the model fail? |
| **Starting point** | Without model | EDA decisions | Trained model with results |
| **Output** | Knowledge + decisions | Features ready for training | Decision for improvement |
| **Lives in** | `notebooks/eda/` | `src/mlsec/data/` | `notebooks/experiments/` |
| **Changes over time** | No — it's stable documentation | Only if decisions change | Yes — iterates with each experiment |

---

## Status

| Dataset | Notebook | EDA | Preprocessing |
|---|---|---|---|
| CSIC 2010 | `notebooks/eda/csic2010_eda.ipynb` | ✅ complete | ✅ `src/mlsec/data/preprocess_csic.py` |
| UNSW-NB15 | `notebooks/eda/unsw_nb15_eda.ipynb` | ✅ complete | ✅ `src/mlsec/data/preprocess_unsw.py` |

---

## EDA — CSIC 2010

**Model:** A — Web Attack Detection  
**File:** `data/raw/csic2010/csic_database.csv`  
**Completed:** 2026-04-06 / 2026-04-10

---

### Dataset structure

- **Shape:** 61,065 rows × 17 columns
- **Original columns:** `Unnamed: 0`, `Method`, `User-Agent`, `Pragma`, `Cache-Control`, `Accept`, `Accept-encoding`, `Accept-charset`, `language`, `host`, `cookie`, `content-type`, `connection`, `lenght`, `content`, `classification`, `URL`

---

### The label

!!! success "Label ready — no transformation needed"
    `classification` is already `int64` with values `[0, 1]`.  
    No mapping needed. Column renamed to `label` for clarity.

- `Unnamed: 0` has the text "Normal"/"Anomalous" — redundant with the label, discard it
- `0` = Normal, `1` = Attack

---

### Class distribution

| Class | Records | % |
|---|---|---|
| Normal (0) | 36,000 | 59% |
| Attack (1) | 25,065 | 41% |

**Mild** imbalance — no SMOTE required. Strategy: `class_weight='balanced'` in the model.

---

### HTTP methods distribution

| Method | Normal | Attack | % Attack |
|---|---|---|---|
| GET | 28,000 | 15,088 | 35% |
| POST | 8,000 | 9,580 | 54% |
| PUT | 0 | **397** | **100%** |

!!! danger "Critical finding — PUT = 100% attacks"
    Every PUT request in the dataset is malicious.  
    `method_is_put` is the most discriminative feature — classifies 397 attacks with perfect precision with a single bit.

**Where attacks live according to method:**

- **GET** → attack is in the `URL` (query string — SQLi, XSS)
- **POST** → attack is in `content` (request body)
- **PUT** → the method itself is the attack indicator

---

### Nulls

| Column | Nulls | % | Cause | Strategy |
|---|---|---|---|---|
| `content` | 43,088 | 70.56% | GET requests have no body | Do not impute — fill with `""` or `0` |
| `lenght` | 43,088 | 70.56% | GET requests have no body | `content_length = 0` for GETs |
| `content-type` | 43,088 | 70.56% | GET requests have no body | Discard — constant among non-nulls |
| `Accept` | 397 | 0.65% | Unknown | Discard — constant column |

The 43,088 nulls correspond exactly to GET requests. **This is not a data quality error** — it's HTTP protocol design (GETs have no body).

---

### Discarded columns

| Column | Reason |
|---|---|
| `Unnamed: 0` | Redundant with label |
| `User-Agent` | Constant — 1 unique value across dataset |
| `Pragma` | Constant — 1 unique value |
| `Cache-Control` | Constant — 1 unique value |
| `Accept` | Constant — 1 unique value |
| `Accept-encoding` | Constant — 1 unique value |
| `Accept-charset` | Constant — 1 unique value |
| `language` | Constant — 1 unique value |
| `content-type` | Constant among non-nulls |
| `host` | 2 values, no useful signal |
| `connection` | 2 values, no useful signal |

**Total: 11 columns dropped** out of 17 original. 6 remain with useful info: `Method`, `cookie`, `lenght`, `content`, `URL`, `label`.

---

### URL length analysis

URL length distributions overlap between normal and attack — both concentrated around 50-100 chars. Attacks have a longer tail (~400 chars vs ~330 in normal).

**Conclusion:** `url_length` alone does not discriminate well, but adds value as a **combined** feature with text indicators.

---

### Correlation of URL indicators with label

!!! warning "Critical finding — URL encoding"
    Special characters `'`, `"`, `<`, `>`, `;` **never appear raw** in URLs.  
    Attackers always encode them (`%27`, `%3C`, etc.) to evade filters.  
    Feature engineering must look for the **percent-encoded** versions, not the literals.

| Indicator | Meaning | Correlation with label |
|---|---|---|
| `url_has_pct27` | `%27` = `'` URL-encoded | **0.183** |
| `url_has_dashdash` | `--` = SQL comment | **0.148** |
| `url_has_script` | XSS keyword | **0.137** |
| `url_has_pct3c` | `%3C` = `<` URL-encoded | **0.124** |
| `url_has_select` | SQL SELECT keyword | 0.050 |
| `url_has_union` | SQL UNION keyword | ~0.000 — discard |
| Raw `'`, `"`, `<`, `>`, `;` | Literal characters | NaN — never appear |

---

### Analysis of content (POST body)

| Metric | Normal | Attack |
|---|---|---|
| Total POST requests | 8,000 | 9,580 |
| Content length — mean | 91.6 chars | 123.2 chars |
| Content length — median | 47.5 chars | 72.0 chars |
| Content length — P75 | 110.5 chars | **243.0 chars** |
| Content length — max | 307 chars | **836 chars** |

POST attacks have **35% longer bodies on average** with a much heavier tail. `content_length` is a discriminative feature for POST requests.

---

### Preprocessing decisions

| Decision | Detail |
|---|---|
| Imbalance | `class_weight='balanced'` — no SMOTE |
| Nulls in content/lenght | `content_length = 0` for GETs — no NaN |
| Method Encoding | One-hot: `method_is_get`, `method_is_post`, `method_is_put` |
| Text indicators | Percent-encoded (`%27`, `%3C`) — no literal chars |
| Normalization | Continuous features only: `url_length`, `content_length` |
| Binary features | No normalization — already 0/1 |

---

### Final features — Model A

| Feature | Source | Type | Importance |
|---|---|---|---|
| `method_is_put` | `Method` | Binary | ⭐⭐⭐ — 100% attacks |
| `method_is_post` | `Method` | Binary | ⭐⭐ — 54% attack rate |
| `method_is_get` | `Method` | Binary | ⭐ — reference |
| `url_has_pct27` | `URL` | Binary | ⭐⭐ — corr 0.183 |
| `url_has_dashdash` | `URL` | Binary | ⭐⭐ — corr 0.148 |
| `url_has_script` | `URL` | Binary | ⭐⭐ — corr 0.137 |
| `url_has_pct3c` | `URL` | Binary | ⭐⭐ — corr 0.124 |
| `url_has_select` | `URL` | Binary | ⭐ — corr 0.050 |
| `url_length` | `URL` | Numerical | ⭐ — useful combined |
| `content_length` | `content` | Numerical | ⭐⭐ — longer POST attacks |
| `content_has_*` | `content` | Binary | pending — same indicators in body |

---

## EDA — UNSW-NB15

**Model:** B — Network Attack Detection  
**Files:** `data/raw/unsw_nb15/UNSW_NB15_training-set.parquet`, `UNSW_NB15_testing-set.parquet`  
**Status:** completed ✅

### Dataset structure

- **Shape:** Train 175,341 × 36 / Test 82,332 × 36
- **Split:** predefined in the parquet — do not modify
- **36 columns:** 33 features + `attack_cat` + `label` + 1 implicit index

### Dtypes — observations

| Type | Columns | Note |
|---|---|---|
| `float32` | `dur`, `rate`, `sload`, `dload`, `sinpkt`, `djit`, etc. | Optimized — not float64 |
| `int8 / int16 / int32` | most integer features | Memory optimized |
| `category` | `proto`, `service`, `state`, `attack_cat` | Ready, no manual conversion |
| `int8` | `label` | Target — 0/1 values ✅ |

The parquet **already comes with optimized dtypes** — a sign of careful processing. Categoricals have native pandas `category` dtype.

**`attack_cat`:** categorical column with the 9 attack types. Used for analysis only — **does not go as model input** (we use binary label).

### The label

- `label` is `int8` with values `[0, 1]` ✅ — ready, no transformation
- `0` = Benign, `1` = Malicious — consistent across project

### Class distribution

| Split | Benign (0) | Malicious (1) | % Malicious |
|---|---|---|---|
| Train | 56,000 | 119,341 | **68.1%** |
| Test | 37,000 | 45,332 | **55.1%** |

!!! warning "Inverse imbalance — more attacks than normal traffic"
    Unlike CSIC 2010 (59% normal), attacks are the majority in train (68%).
    Also the ratio is **different between train and test** — train has proportionally more attacks.
    This is unusual but documented in the original UNSW-NB15 paper.

**Imbalance strategy:** to be defined in EDA — evaluate `class_weight='balanced'` vs SMOTE.
With 68/32 the imbalance is moderate-high — SMOTE might be necessary.

### Attack categories (attack_cat)

For analysis only — does not go as model input. We use binary label (0/1).

| Category | Records | % of attacks | Description |
|---|---|---|---|
| Generic | 40,000 | 33.5% | Unclassified generic attacks |
| Exploits | 33,393 | 28.0% | Exploitation of known vulnerabilities |
| Fuzzers | 18,184 | 15.2% | Malformed input to find bugs |
| DoS | 12,264 | 10.3% | Denial of Service |
| Reconnaissance | 10,491 | 8.8% | Network scanning and recon |
| Analysis | 2,000 | 1.7% | Traffic analysis / sniffing |
| Backdoor | 1,746 | 1.5% | Unauthorized remote access |
| Shellcode | 1,133 | 0.9% | Malicious code execution |
| Worms | 130 | 0.1% | Self-propagating malware |

!!! warning "Worms severely under-represented"
    130 records vs 40,000 for Generic — 1:307 ratio. Even using a binary label, the model will have very few examples of Worm patterns. Low recall on this category is expected.

**Top 3 categories make up 76.7% of attacks:** Generic + Exploits + Fuzzers.

### Nulls

!!! success "No nulls — all 36 columns are complete"
    No imputation strategy needed for UNSW-NB15.

**Note:** the `-` value in the `service` column is not a technical null — it's its own category meaning "no identified service". Analyzed in the categorical features section.

### Categorical features

#### proto — 133 unique values

!!! warning "High cardinality — requires reduction"
    Direct one-hot encoding would generate 133 columns. Strategy: keep top-10 most frequent + `other` category for the rest.

| Value | Records | % | Description |
|---|---|---|---|
| tcp | 79,946 | 45.6% | Transmission Control Protocol |
| udp | 63,283 | 36.1% | User Datagram Protocol |
| unas | 12,084 | 6.9% | Unassigned protocol |
| arp | 2,859 | 1.6% | Address Resolution Protocol |
| ospf | 2,595 | 1.5% | Routing protocol |
| other 128 | ~14,574 | 8.3% | → group into `other` |

TCP + UDP + unas = **88.6% of traffic**. The rest is grouped.

#### service — 13 unique values

Direct one-hot encoding. `-` **is not a null** — it's the "no identified service" category and is the most frequent (53.6%).

| Value | Records | % |
|---|---|---|
| `-` | 94,168 | 53.6% |
| dns | 47,294 | 27.0% |
| http | 18,724 | 10.7% |
| smtp | 5,058 | 2.9% |
| ftp-data | 3,995 | 2.3% |
| other 8 | ~6,102 | 3.5% |

#### state — 9 unique values

Direct one-hot encoding. INT + FIN + CON = 99% of traffic.

| Value | Records | % | Description |
|---|---|---|---|
| INT | 82,275 | 46.9% | Intermediate — connection in progress |
| FIN | 77,825 | 44.4% | Connection finished normally |
| CON | 13,152 | 7.5% | UDP/ICMP — established connection |
| RST | 83 | 0.05% | Reset — connection terminated abruptly |
| other 5 | 16 | ~0% | Extremely rare cases |

#### Encoding strategy per column

| Column | Cardinality | Strategy |
|---|---|---|
| `proto` | 133 | Top-10 + `other` category → one-hot |
| `service` | 13 | Direct one-hot (13 columns) |
| `state` | 9 | Direct one-hot (9 columns) |

### Descriptive statistics — numerical features

#### Extreme outliers

Several features have mean >> median — distributions with very heavy tails. StandardScaler is not suitable for these features.

| Feature | Median | Mean | Maximum | Observation |
|---|---|---|---|---|
| `sbytes` | 430 | 8,844 | 12,965,230 | Extreme tail — bytes sent |
| `dbytes` | 164 | 14,928 | 14,655,550 | Extreme tail — bytes received |
| `sload` | 879,674 | 73,454,030 | 5,988,000,000 | Extreme tail — source load |
| `dload` | 1,447 | 671,205 | 22,422,730 | Extreme tail — dest load |
| `response_body_len` | 0 | 2,144 | 6,558,056 | P75=0, very sparse |
| `sjit` | 0 | 4,976 | 1,460,480 | Extreme jitter |
| `rate` | 3,225 | 95,406 | 1,000,000 | Max=1M exact — possible artificial cap |

**Normalization strategy:** `RobustScaler` (uses median and IQR, resistant to outliers) or log-transform + StandardScaler for features with heaviest tails.

#### Sparse features (median=0, P75=0)

These features are zero for most traffic — they only activate in specific cases:

`trans_depth`, `response_body_len`, `is_ftp_login`, `ct_ftp_cmd`, `ct_flw_http_mthd`, `tcprtt`, `synack`, `ackdat`, `sloss`, `dloss`, `sjit`, `djit`

They are still useful — when activated, they can be highly discriminative.

#### Distributions by class — flow feature histograms

| Feature | Observed pattern | Discriminative power |
|---|---|---|
| `rate` | Attacks uniformly distributed up to 1M. Normal concentrated near 0 | ⭐⭐⭐ High |
| `sload` | Attacks with more multimodal distribution. Normal more concentrated | ⭐⭐ Medium |
| `sbytes` | Both classes concentrated near 0, attacks have heavier tail | ⭐ Low-medium |
| `dur` | Both concentrated near 0. Attacks tend to be shorter | ⭐ Low-medium |
| `dbytes` | **Normal has MORE received bytes than attacks** | ⭐⭐ Medium |
| `dload` | **Normal completely dominates** — legit traffic downloads more data | ⭐⭐ Medium |

!!! info "Inverse pattern in dbytes and dload"
    Normal traffic has more received bytes than attacks. This makes sense: legitimate traffic downloads data (HTTP responses, DNS replies). Many attacks are scans or probes that don't receive a response — they send packets but get nothing back.

**Normalization strategy confirmed:** `RobustScaler` for all flow features — extremely skewed distributions, StandardScaler would be rendered useless by outliers.

#### Anomalies to investigate

| Feature | Issue | Decision |
|---|---|---|
| `is_ftp_login` | Max=4 — should be binary 0/1 | Investigate — possible error or count |
| `stcpb` / `dtcpb` | TCP sequence numbers up to 4.29B — random by design | Candidates to discard |
| `rate` | Max=1,000,000 exact | Possible artificial cap — verify |
| `swin` / `dwin` | Bounded 0-255 (TCP window size) | MinMaxScaler or no normalization |

### Feature correlation with label

#### Top features — positive correlation (higher value → more likely attack)

| Feature | Correlation | Interpretation |
|---|---|---|
| `ct_dst_sport_ltm` | **0.357** | Count of recent connections to same dest/port — attacks generate many connections |
| `rate` | **0.338** | Packets per second rate — attacks have higher/uniform rate |
| `ct_src_dport_ltm` | **0.306** | Count of recent connections from same source — scanning pattern |
| `sload` | 0.183 | Source load — attacks send more data |
| `ackdat` | 0.097 | Time between SYN-ACK and ACK — anomalous TCP pattern |
| `tcprtt` | 0.082 | TCP round-trip time |
| `synack` | 0.058 | SYN-ACK time |

#### Top features — negative correlation (higher value → more likely normal traffic)

| Feature | Correlation | Interpretation |
|---|---|---|
| `dload` | **-0.394** | Normal traffic downloads more data — attacks are probes with no response |
| `dmean` | **-0.342** | Mean received packet size — higher in legitimate traffic |
| `swin` | **-0.334** | TCP window size source — higher in established legitimate connections |
| `dwin` | **-0.320** | TCP window size dest — higher in legitimate connections |
| `stcpb` | -0.255 | TCP sequence number — unexpected correlation, **do not discard yet** |

#### Features with correlation ~0 → candidates to discard

`sloss` (-0.001), `sjit` (-0.007), `smean` (-0.011), `ct_ftp_cmd` (-0.011)

> **Important:** low linear correlation does not mean the feature is useless for non-linear models like Random Forest. Confirm importance post-training.

#### Decision on stcpb / dtcpb

`stcpb` shows -0.255 correlation — unexpected for a TCP sequence number that should be random. There may be a pattern in how the dataset was generated. **Keep in the initial model** and evaluate feature importance post-training.

### Correlation among features (redundancy heatmap)

Correlation analysis among the top 15 features by label correlation. Goal: identify redundant pairs to simplify the model.

#### Highly correlated pairs (> 0.9) — candidates for elimination

| Pair | Correlation | Decision |
|---|---|---|
| `swin` / `dwin` | **0.99** | Discard `dwin` — almost identical (TCP window size source/dest) |
| `dpkts` / `dloss` | **0.98** | Discard `dloss` — derived from `dpkts` |
| `is_sm_ips_ports` / `sinpkt` | **0.94** | Discard `is_sm_ips_ports` — `sinpkt` has higher label correlation |
| `ct_dst_sport_ltm` / `ct_src_dport_ltm` | **0.91** | Keep both — though correlated, they capture different perspectives (dest vs source) |

#### Moderately correlated pairs (0.6–0.9) — keep both

| Pair | Correlation | Note |
|---|---|---|
| `stcpb` / `dtcpb` | **0.65** | Keep — moderate correlation, different perspectives |
| `rate` / `ct_dst_sport_ltm` | ~0.5 | Keep — rate is packet rate, ct_ is connection count |

!!! info "Why eliminate correlated features"
    Two features with 0.99 correlation provide almost the same information to the model. Keeping them does not improve prediction but adds noise and dimensionality. In Random Forest this has little practical impact, but it's good practice to reduce redundancies before training.

#### Features discarded due to redundancy

| Feature | Reason | Replaced by |
|---|---|---|
| `dwin` | 0.99 correlation with `swin` | `swin` |
| `dloss` | 0.98 correlation with `dpkts` | `dpkts` |
| `is_sm_ips_ports` | 0.94 with `sinpkt`, lower label correlation | `sinpkt` |

### Constant or low variance features

Numerical features with few unique values (< 10) — candidates to discard or treat specially:

| Feature | Unique values | Real type | Decision |
|---|---|---|---|
| `is_sm_ips_ports` | 2 | Binary | **Discard** — already identified as redundant with `sinpkt` (correlation 0.94) |
| `dwin` | 7 | Almost binary | **Discard** — already identified as redundant with `swin` (correlation 0.99) |
| `is_ftp_login` | 4 | Should be binary | **Keep with caution** — max=4 is an anomaly (should be 0/1). It might be a count instead of a binary flag. Validate with post-training feature importance |
| `ct_ftp_cmd` | 4 | Count | **Keep** — sparse but potentially discriminative for FTP connections. ~0 correlation globally doesn't mean it's useless in Random Forest |

!!! info "Low variance ≠ useless"
    A binary feature or one with few unique values can be highly discriminative if those values are distributed differently between classes. `is_sm_ips_ports` and `dwin` are discarded due to **redundancy**, not just low variance.

### Final decisions — UNSW-NB15

| Decision | Detail |
|---|---|
| **Normalization** | `RobustScaler` for all continuous numerical features |
| **Encoding** | Top-10+other for `proto`, direct one-hot for `service` and `state` |
| **Imbalance** | Evaluate `class_weight='balanced'` first — 68/32 imbalance |
| **Nulls** | No imputation necessary — complete dataset |
| **Discarded features** | `dwin`, `dloss`, `is_sm_ips_ports` (redundant) |
| **Features to monitor** | `stcpb`, `dtcpb` — unexpected correlation, validate with feature importance |
| **attack_cat** | For analysis only — does not go as model input |

### Analysis plan

| Analysis | Tool | Expected Output |
|---|---|---|
| `attack_cat` distribution | `value_counts()` + barplot | Understand the 9 attack types |
| Class distribution | `label.value_counts()` | Confirm 68/32 imbalance |
| Correlation among numerical features | heatmap | Redundant features to eliminate |
| Outliers in flow features | boxplot + IQR | Normalization strategy |
| Unique values in categoricals | `nunique()` | Encoding strategy |
| Nulls / `-` values in `service` | `isnull()` + `value_counts()` | Imputation or own category |

---

## Completion checklist

- [x] Label confirmed as 0/1 — CSIC 2010 ✅
- [x] CSIC 2010 features defined ✅
- [x] CSIC 2010 nulls strategy ✅
- [x] CSIC 2010 normalization strategy ✅
- [x] CSIC 2010 imbalance strategy — `class_weight='balanced'` ✅
- [x] Label confirmed as 0/1 — UNSW-NB15 ✅
- [x] UNSW-NB15 features analyzed — label correlation + redundancies ✅
- [x] UNSW-NB15 nulls strategy — no nulls, no imputation needed ✅
- [x] UNSW-NB15 normalization strategy — RobustScaler ✅
- [x] UNSW-NB15 imbalance strategy — evaluate class_weight='balanced' ✅
- [x] Redundant features identified — dwin, dloss, is_sm_ips_ports discarded ✅
- [x] `docs/models.md` updated with all UNSW-NB15 decisions ✅
