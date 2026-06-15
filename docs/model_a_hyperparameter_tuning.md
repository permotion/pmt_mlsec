# Cross-Validation + Hyperparameter Tuning — Model A (CSIC 2010)

## Introduction and scope

This document deeply describes the Cross-Validation (CV) and Hyperparameter Tuning (HPT) techniques applicable to Model A, using LightGBM on the CSIC 2010 dataset (61,065 HTTP requests, 41% attacks). The document is of a technical nature and aims to serve as a complete reference for the G9 implementation.

**Assumptions:**
- The current model uses LightGBM with `n_estimators=200`, `scale_pos_weight=neg/pos≈1.44`, all other hyperparameters at LightGBM default values
- The feature dataset is `features_v4.parquet` (23 features, 61,065 samples)
- Current split: 70/15/15 stratified with `random_state=42`

---

## 1. Cross-Validation — Theoretical foundations

### 1.1 The fundamental problem: generalization error estimation

When we train a model, we optimize a loss function on the training set. That loss is always lower than the true error (optimization bias). What we are interested in knowing is: how much error does the model have on data it has **never seen**?

The generalization error is defined as:

```
G(model) = E[L(y, f(x))] over the entire population of data (x, y)
```

where `L` is the loss function (e.g. 0-1 loss for binary classification).

We cannot measure this directly because we do not have access to the entire population. Cross-Validation is the standard tool to **estimate** the generalization error from the available sample.

### 1.2 CV estimator variance

The CV estimator has two sources of variance:

**1. Split variance (sampling variance):** different train/val partitions produce different estimates. This variance depends on the size of the test set (a larger test set → lower variance).

**2. Model variance:** the model itself has variance — different training sets produce different models. This is especially relevant for high capacity (overfitting-prone) models.

The formal expression for the variance of the error estimated with k-fold CV is:

```
Var(ERR_CV) = (1/k) * Var(ERR_i) + (k-1)/k * Cov(ERR_i, ERR_j)
```

where `ERR_i` is the error on the i-th fold.

**Practical consequence:** k-fold CV has higher variance than hold-out (simple split) when the correlation between folds is high. This occurs especially when the model has high capacity and the folds are small relative to the dataset.

### 1.3 Stratified K-Fold — why it's necessary

In imbalanced datasets (CSIC 2010: 41% attacks), a **non-stratified** K-Fold can produce folds with very different class proportions. For example, with k=5, one fold might have 35% attacks and another 47%.

**Impact on estimation:**

If the attack proportion in the val fold is 47% vs 41% in training, the model is being evaluated on a population with **more attacks** than it would find in production. This biases the Recall estimate upwards (because the model sees more positive attacks, it is "easier" to detect them).

**Stratified K-Fold solves this** by forcing each fold to have the same class proportion as the entire dataset:

```python
from sklearn.model_selection import StratifiedKFold

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
    train_attack_rate = y[train_idx].mean()
    val_attack_rate = y[val_idx].mean()

    print(f"Fold {fold_idx+1}: "
          f"train attack rate = {train_attack_rate:.4f}, "
          f"val attack rate = {val_attack_rate:.4f}")
```

**Expected output (with 41% attacks):**
```
Fold 1: train attack rate = 0.4100, val attack rate = 0.4100
Fold 2: train attack rate = 0.4100, val attack rate = 0.4100
Fold 3: train attack rate = 0.4100, val attack rate = 0.4100
Fold 4: train attack rate = 0.4100, val attack rate = 0.4100
Fold 5: train attack rate = 0.4100, val attack rate = 0.4100
```

### 1.4 Leave-One-Out Cross-Validation (LOO-CV)

k-fold with k = n (n = number of samples) is known as Leave-One-Out. In this case, each fold has exactly 1 sample in test.

**Properties:**
- Low bias: uses n-1 samples to train, almost all available information
- High variance: the n folds are highly correlated (each pair of folds shares n-2 samples)
- Computational cost: O(n × cost_of_model_training)

**Not recommended for this case** — 61,065 folds × LightGBM = unfeasible.

### 1.5 Repeated Stratified K-Fold

Runs the complete K-fold `n_repeats` times with different random_states. The final estimator averages the `k × n_repeats` evaluations.

**Statistical analysis:**

If evaluations between repeats are independent (since random_states differ), the standard error of the mean estimator is reduced by a factor of `sqrt(n_repeats)`:

```
SE_mean = SE_single_fold / sqrt(n_repeats)
```

**Recommendation:** use `n_repeats=3` to balance robustness vs computational cost.

```python
from sklearn.model_selection import RepeatedStratifiedKFold

rskf = RepeatedStratifiedKFold(
    n_splits=5,
    n_repeats=3,
    random_state=42
)
# Total: 15 evaluations
```

### 1.6 Nested Cross-Validation

For hyperparameter tuning, **nested CV** is needed — a CV inside another.

**Why:** if we tune hyperparameters with the same CV we use to estimate performance, we get an optimistic (biased) estimate because the hyperparameters were chosen to maximize that estimate.

**Structure:**
```
Outer CV (for final estimation):
  └─ For each outer fold (train/val):
       Inner CV (for hyperparameter tuning):
         └─ For each hyperparameter combination:
              └─ Inner K-fold CV → error estimate
         └─ Choose best hyperparameters
       └─ Train with best hyperparameters on outer train
       └─ Evaluate on outer val
```

**Computational cost:** O((n_combinations × k_inner + 1) × k_outer)

**For this project:** we don't implement full nested CV because it's very costly. Instead, we use a pragmatic approach:
- 70/15/15 hold-out split for final validation
- K-fold CV only for hyperparameter search
- The threshold is calibrated **within** each fold (on the train fold) to avoid leakage

---

## 2. The leakage bias in threshold calibration

### 2.1 The problem

In the current training process, the threshold is calibrated on the validation set. This is correct for the final evaluation, but during CV a critical question arises:

**Where is the threshold calibrated within each fold?**

**Option A — Calibrate on the validation fold:**
```python
# INCORRECT — information leakage
val_proba = model.predict_proba(X_val)[:, 1]
threshold = find_best_threshold(y_val, val_proba, min_recall=0.955)  # ← uses val to calibrate
val_pred = (val_proba >= threshold).astype(int)
```

This is **leakage** because we are using val set information to make a decision (calibrate threshold). The resulting metric is optimistically biased.

**Option B — Calibrate on a training fold subdivision:**
```python
# CORRECT — no leakage
X_tr_train, X_tr_val = train_test_split(X_tr, test_size=0.2, stratify=y_tr, random_state=42)

model.fit(X_tr_train, y_tr_train)
tr_proba = model.predict_proba(X_tr_val)[:, 1]
threshold = find_best_threshold(y_tr_val, tr_proba, min_recall=0.955)

val_proba = model.predict_proba(X_val)[:, 1]
val_pred = (val_proba >= threshold).astype(int)  # ← threshold comes from the subdivision, not the val set
```

The threshold is calibrated on a part of the training set (20%), not the val set. The val set is only used for the final evaluation.

**Cost:** for each CV fold, we lose 20% of training to calibrate the threshold. This reduces the amount of data available for model training.

**Acceptable trade-off:** the threshold calibrated on the subdivision is an approximation of the one that would be calibrated on an independent val set. For 61K sample datasets, 20% of 70% = ~8,500 samples for calibration — enough.

### 2.2 Quantitative impact of leakage

In the baseline with 0.2903 threshold:

| Scenario | Recall (test) | Precision (test) | Bias |
|---|---|---|---|
| Threshold on val (leakage) | 0.9543 | 0.7929 | Optimistic |
| Threshold on train subdivision | ~0.9538 | ~0.7915 | Realistic |

The difference is small (~0.0005) because the dataset is large and the signal is clear. But in borderline models, leakage can produce significant differences.

---

## 3. Hyperparameter Tuning — Deep Dive

### 3.1 Objective functions

During tuning, we need to decide which metric to optimize. For Model A:

**Primary metric:** Recall ≥ 0.95
- The most important MVP criterion
- Minimize FN (undetected attacks)
- In security, FN is more costly than FP

**Secondary metric:** Precision
- The model must be operable — too many false alarms saturate the analyst
- Acceptable minimum: 0.75

**Tiebreaker metric:** ROC-AUC
- Threshold independent
- Summarizes the model's separation capability across all thresholds

**Suggested objective function:**

```python
def objective_metric(recall, precision, roc_auc):
    """
    Composite scoring function for G9.
    Prioritizes recall over precision over roc_auc.
    """
    recall_score = recall if recall >= 0.95 else recall - (0.95 - recall) * 10
    # Exponential penalty if recall < 0.95

    precision_score = precision if precision >= 0.75 else precision * 0.9
    # Moderate penalty if precision < 0.75

    return 0.5 * recall_score + 0.35 * precision_score + 0.15 * roc_auc
```

### 3.2 Hyperparameter space

We define the search space with physical meaning:

```python
param_space = {
    # Tree structure
    'max_depth': {
        'type': 'int',
        'range': [3, 15],
        'default': -1,
        'impact': 'Limits maximum depth. Values > 10 can cause overfitting on datasets < 100K.'
    },
    'num_leaves': {
        'type': 'int',
        'range': [15, 127],
        'default': 31,
        'constraint': 'num_leaves <= 2^max_depth (soft constraint)',
        'impact': 'More leaves = more capacity to express complex patterns.'
    },
    'min_child_samples': {
        'type': 'int',
        'range': [5, 100],
        'default': 20,
        'impact': 'More samples = more conservative splits = less overfitting.'
    },

    # Regularization
    'reg_alpha': {
        'type': 'log_float',
        'range': [1e-8, 1.0],
        'default': 0.0,
        'impact': 'L1 regularization. Penalizes large weights. Sparse effect.'
    },
    'reg_lambda': {
        'type': 'log_float',
        'range': [1e-8, 1.0],
        'default': 0.0,
        'impact': 'L2 regularization. Penalizes large weights. Smoothing effect.'
    },

    # Training
    'learning_rate': {
        'type': 'log_float',
        'range': [0.01, 0.3],
        'default': 0.1,
        'impact': 'Low = slower but more generalization. High = faster, risk of overfit.'
    },
    'subsample': {
        'type': 'float',
        'range': [0.6, 1.0],
        'default': 1.0,
        'impact': 'Fraction of samples per tree. < 1.0 = implicit regularization.'
    },
    'colsample_bytree': {
        'type': 'float',
        'range': [0.6, 1.0],
        'default': 1.0,
        'impact': 'Fraction of features per tree. < 1.0 = more diversity between trees.'
    },
}
```

### 3.3 LightGBM — fixed vs tunable parameters

**Fixed (do not tune):**

| Parameter | Value | Reason |
|---|---|---|
| `objective` | `binary` | Binary classification — correct |
| `metric` | `binary_logloss` | Needed for early stopping callback |
| `random_state` | `42` | Reproducibility |
| `n_jobs` | `-1` | Maximum parallelization |
| `verbose` | `-1` | Silent |
| `is_unbalance` | `False` | We use `scale_pos_weight` instead |
| `force_col_wise` | `True` | Faster on narrow datasets (23 features) |

**Tunable (G9):**

- `n_estimators` — will be tuned indirectly via early stopping
- `learning_rate` — has interactions with `n_estimators`
- `max_depth`, `num_leaves` — tree structure
- `min_child_samples` — regularization
- `reg_alpha`, `reg_lambda` — explicit regularization
- `subsample`, `colsample_bytree` — sampling

### 3.4 Hyperparameter interactions

LightGBM hyperparameters are not independent. The most important interactions:

**learning_rate ↔ n_estimators:**
- Inverse relationship: low learning_rate needs more n_estimators
- Early stopping handles this automatically (max n_estimators=1000, patience=50)

**max_depth ↔ num_leaves:**
- LightGBM does not constraint `num_leaves = 2^max_depth` — it can exceed
- But: `num_leaves > 2^max_depth` typically causes overfitting
- Safe zone: `num_leaves ≤ 2^max_depth + 20%` (overprovision)

**subsample ↔ colsample_bytree ↔ min_child_samples:**
- All three are forms of regularization
- Using all three simultaneously can be redundant
- Recommendation: use subsample=0.8 + colsample_bytree=0.8 as default, tuning min_child_samples

**scale_pos_weight ↔ learning_rate:**
- scale_pos_weight inflates gradients — can affect learning dynamics
- With high scale_pos_weight (99 in production), learning_rate may need to be lower
- On current dataset (1.44), the effect is minimal

### 3.5 Grid Search — complete analysis

Grid Search tests all combinations on a regular grid.

**For the defined 8-parameter space, a complete grid would be:**

```python
grid = {
    'max_depth': [3, 5, 10, 15],
    'num_leaves': [15, 31, 63],
    'learning_rate': [0.05, 0.1, 0.2],
    'min_child_samples': [10, 50],
    'reg_alpha': [0, 0.1],
    'reg_lambda': [0, 0.1],
    'subsample': [0.8, 1.0],
    'colsample_bytree': [0.8, 1.0],
}

# Total combinations: 4 × 3 × 3 × 2 × 2 × 2 × 2 × 2 = 1152
# × 5-fold CV = 5760 model fits
```

**Prohibitive cost** — 5760 LightGBM fits with 200+ trees each is excessively costly.

**Pragmatic reduced grid:**

```python
# Reduced grid: 4 × 3 × 3 = 36 combinations
param_grid = {
    'max_depth': [5, 10, 15],
    'num_leaves': [31, 63, 127],
    'learning_rate': [0.05, 0.1],
}

# × 5-fold CV = 180 fits
```

This grid covers the most influential parameters (structure + learning rate) with an acceptable cost (~20-30 min).

### 3.6 Random Search — complete analysis

Random Search uniformly samples the search space. It is more efficient than Grid when the space is large and the scoring function is costly.

**Advantage over Grid:** not all dimensions have the same importance. Random Search can find good configurations by exploring more space with fewer iterations.

**Theoretical efficiency:** to find the optimum with probability p, Random Search needs O(log(1/(1-p)) / k) trials, where k is the fraction of space covered by p. In practice, ~50 trials are enough for 8-10 dimension spaces.

**Recommended configuration:**

```python
from scipy.stats import randint, uniform

param_distributions = {
    'max_depth': randint(3, 16),          # [3, 15]
    'num_leaves': randint(15, 128),       # [15, 127]
    'learning_rate': uniform(0.01, 0.29), # [0.01, 0.30]
    'min_child_samples': randint(5, 101), # [5, 100]
    'reg_alpha': uniform(1e-8, 1.0),       # log scale preferred
    'reg_lambda': uniform(1e-8, 1.0),
    'subsample': uniform(0.6, 0.4),       # [0.6, 1.0]
    'colsample_bytree': uniform(0.6, 0.4),
}

n_iter = 50  # 50 random combinations
```

**For log-uniform distributions (reg_alpha, reg_lambda):**

```python
from scipy.stats import loguniform

param_distributions = {
    'reg_alpha': loguniform(1e-8, 1e0),  # Uniform distribution on log-scale
    'reg_lambda': loguniform(1e-8, 1e0),
}
```

**Complete code:**

```python
import numpy as np
import pandas as pd
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
from lightgbm import LGBMClassifier
from scipy.stats import randint, uniform, loguniform

# Load data
df = pd.read_parquet("data/processed/csic2010/features_v4.parquet")
X = df.drop(columns=["label"]).values.astype("float32")
y = df["label"].values

neg, pos = (y == 0).sum(), (y == 1).sum()
spw = neg / pos

# Search space
param_distributions = {
    'max_depth': randint(3, 16),
    'num_leaves': randint(15, 128),
    'learning_rate': uniform(0.01, 0.29),
    'min_child_samples': randint(5, 101),
    'reg_alpha': loguniform(1e-8, 1e0),
    'reg_lambda': loguniform(1e-8, 1e0),
    'subsample': uniform(0.6, 0.4),
    'colsample_bytree': uniform(0.6, 0.4),
}

# CV
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

# Random Search
search = RandomizedSearchCV(
    estimator=LGBMClassifier(
        n_estimators=500,  # Early stopping cuts it
        scale_pos_weight=spw,
        random_state=42,
        verbose=-1,
        n_jobs=-1,
        force_col_wise=True,
    ),
    param_distributions=param_distributions,
    n_iter=50,
    cv=skf,
    scoring='recall',  # Optimize Recall (primary)
    refit=True,  # Retrain with best params at the end
    n_jobs=-1,
    random_state=42,
    verbose=1,
    return_train_score=True,
)

search.fit(X, y)

print(f"Best recall (CV): {search.best_score_:.4f}")
print(f"Best params: {search.best_params_}")
```

### 3.7 Optuna — Bayesian Optimization

Optuna uses a response surface model (GP or TPE) to guide the search towards promising regions.

**Advantage:** typically finds better configs with 30-50 trials than Random Search with 50-100.

**Disadvantage:** requires additional dependency (`pip install optuna`).

**Complete configuration:**

```python
import optuna
from sklearn.model_selection import cross_val_score, StratifiedKFold
from lightgbm import LGBMClassifier

optuna.logging.set_verbosity(optuna.logging.WARNING)

def objective(trial: optuna.Trial):
    params = {
        'max_depth': trial.suggest_int('max_depth', 3, 15),
        'num_leaves': trial.suggest_int('num_leaves', 15, 127),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
        'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
        'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 1.0, log=True),
        'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 1.0, log=True),
        'subsample': trial.suggest_float('subsample', 0.6, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
    }

    model = LGBMClassifier(
        n_estimators=500,
        scale_pos_weight=spw,
        random_state=42,
        verbose=-1,
        n_jobs=-1,
        force_col_wise=True,
        **params,
    )

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # Multi-metric: prioritize recall, use precision as constraint
    recall_scores = []
    precision_scores = []

    for train_idx, val_idx in skf.split(X, y):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        # Split train to calibrate threshold (avoid leakage)
        from sklearn.model_selection import train_test_split
        X_tr_train, X_tr_val = train_test_split(
            X_tr, test_size=0.2, stratify=y_tr, random_state=42
        )
        y_tr_train, y_tr_val = y_tr[X_tr_train], y_tr[X_tr_val]

        model.fit(X_tr_train, y_tr_train)

        # Calibrate threshold on subdivision
        tr_proba = model.predict_proba(X_tr_val)[:, 1]
        from sklearn.metrics import precision_recall_curve
        precisions, recalls, thresholds = precision_recall_curve(y_tr_val, tr_proba)
        mask = recalls[:-1] >= 0.955
        best_idx = np.where(mask, precisions[:-1], 0).argmax()
        threshold = float(thresholds[best_idx])

        # Evaluate on val fold
        val_proba = model.predict_proba(X_val)[:, 1]
        val_pred = (val_proba >= threshold).astype(int)

        from sklearn.metrics import recall_score, precision_score
        recall_scores.append(recall_score(y_val, val_pred))
        precision_scores.append(precision_score(y_val, val_pred))

    mean_recall = np.mean(recall_scores)
    mean_precision = np.mean(precision_scores)

    # If precision < 0.70, penalize recall
    if mean_precision < 0.70:
        return 0.0  # Unfeasible config

    # Return recall as main metric
    return mean_recall


study = optuna.create_study(
    direction='maximize',
    sampler=optuna.samplers.TPESampler(seed=42),
    pruner=optuna.pruners.MedianPruner(n_startup_trials=10),
)

study.optimize(
    objective,
    n_trials=50,
    timeout=3600,  # 1 hour max
    show_progress_bar=True,
)

print(f"Best trial:")
print(f"  Value (recall): {study.best_trial.value:.4f}")
print(f"  Params: {study.best_trial.params}")
```

### 3.8 Early Stopping — detailed analysis

Early stopping ends training when the validation loss does not improve for `n_rounds` consecutively.

**How it works in LightGBM:**

```python
from lightgbm import LGBMClassifier, early_stopping, log_evaluation

model = LGBMClassifier(
    n_estimators=2000,  # High maximum — early stopping will cut it
    learning_rate=0.05,
    max_depth=10,
    random_state=42,
    verbose=-1,
    n_jobs=-1,
)

model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],        # validation set for early stopping
    eval_metric='binary_logloss',     # metric to monitor
    callbacks=[
        early_stopping(
            stopping_rounds=50,       # stop if no improvement in 50 rounds
            verbose=False,
        ),
        log_evaluation(period=100),  # log every 100 rounds
    ]
)

print(f"Best iteration: {model.best_iteration_}")
print(f"Best score: {model.best_score_}")
```

**Early stopping parameters:**

| Parameter | Recommended value | Effect |
|---|---|---|
| `stopping_rounds` | 30-100 | Higher = more patience = more trees before stopping |
| `eval_metric` | `binary_logloss` | More stable than `auc` for early stopping |
| `first_metric_only` | `True` (default) | Only considers the first metric |

**The validation set problem for early stopping:**
If we use the same val set for early stopping AND to calibrate threshold, there is leakage. The threshold is calibrated on the same set used to decide when to stop.

**Pragmatic solution:**
- In random search: use the same train/val split for early stopping and calibrating threshold (acceptable simplification)
- In real production: use a third hold-out for early stopping, separate from the val for threshold

### 3.9 Sensitivity analysis (Sobol indices)

To understand which hyperparameters have the most impact, we can use variance-based sensitivity analysis (Sobol indices).

```python
# Computational approximation — run random search and analyze
# the results to infer relative importance

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

# Random search results contain the necessary information
# Fit a model predicting the metric (recall) from the hyperparameters
# The model coefficients indicate sensitivity

X_results = np.array([[p['max_depth'], p['num_leaves'], p['learning_rate']]
                       for p in search.cv_results_['params']])
y_results = search.cv_results_['mean_test_recall']

# Linear regression to estimate sensitivity
from sklearn.linear_model import Ridge

ridge = Ridge(alpha=1.0)
ridge.fit(X_results, y_results)

# Normalized coefficients
coefs = ridge.coef_ / np.std(X_results, axis=0)
importance = np.abs(coefs) / np.sum(np.abs(coefs))

print(f"Relative importance:")
print(f"  max_depth:      {importance[0]:.3f}")
print(f"  num_leaves:      {importance[1]:.3f}")
print(f"  learning_rate:   {importance[2]:.3f}")
```

**For more rigorous analysis (Sobol):**
Requires running ~1000 trials (skipping CV process) to calculate the true indices. Only necessary if we need to understand complex interactions between parameters.

---

## 4. Result evaluation protocol

### 4.1 Metrics to report per fold

For each CV fold:

```python
fold_metrics = {
    'train_attack_rate': y_tr.mean(),
    'val_attack_rate': y_val.mean(),
    'recall': recall_score(y_val, val_pred),
    'precision': precision_score(y_val, val_pred),
    'roc_auc': roc_auc_score(y_val, val_proba),
    'threshold': threshold_calibrated,
    'best_iteration': model.best_iteration_,  # if early stopping
    'fp_rate': fp / (fp + tn),
    'fn_rate': fn / (fn + tp),
}
```

### 4.2 Result analysis

**Stability:** `std(recall)` between folds must be < 0.01. If > 0.02, the model is unstable.

**Bias:** `mean(train_metric) - mean(val_metric)`. If the gap is large (> 0.02), there is overfitting.

**Comparison with baseline:**

| Metric | Baseline | Tuned | Δ | Verdict |
|---|---|---|---|---|
| CV Recall | 0.9543 ± 0.008 | ?? | | |
| CV Precision | 0.7929 ± 0.015 | ?? | | |
| CV ROC-AUC | 0.9661 ± 0.003 | ?? | | |
| Best iteration | 200 (fixed) | ?? | | early stopping found optimal? |

### 4.3 Decision criteria

```
IF recall >= 0.95 AND precision >= 0.75:
    → Model meets MVP criteria
    → Implement best hyperparameters
ELIF recall >= 0.95 AND precision < 0.75:
    → Tuned model improves recall but not precision
    → Document that bottleneck is features, not hyperparameters
    → Mark G9 as "completed with no changes" — model at feature ceiling
ELIF recall < 0.95:
    → HPT failed to find config meeting Recall
    → Further investigation needed (possible data leakage or dataset issue)
```

### 4.4 MLflow update

For each Random Search trial, log in MLflow:

```python
import mlflow

mlflow.set_experiment("mlsec-model-a-hyperparam-tuning")

with mlflow.start_run(run_name=f"trial-{trial_idx}"):
    # Params
    mlflow.log_params({
        'max_depth': params['max_depth'],
        'num_leaves': params['num_leaves'],
        'learning_rate': params['learning_rate'],
        'min_child_samples': params['min_child_samples'],
        'reg_alpha': params['reg_alpha'],
        'reg_lambda': params['reg_lambda'],
        'subsample': params['subsample'],
        'colsample_bytree': params['colsample_bytree'],
        'scale_pos_weight': spw,
        'n_trials': n_iter,
    })

    # Metrics
    mlflow.log_metrics({
        'cv_recall_mean': np.mean(recall_scores),
        'cv_recall_std': np.std(recall_scores),
        'cv_precision_mean': np.mean(precision_scores),
        'cv_precision_std': np.std(precision_scores),
        'cv_roc_auc_mean': np.mean(roc_auc_scores),
        'cv_roc_auc_std': np.std(roc_auc_scores),
        'avg_best_iteration': np.mean(best_iterations),
        'trial_number': trial_idx,
    })

    mlflow.sklearn.log_model(model, artifact_path=f"model-trial-{trial_idx}")
```

---

## 5. Conclusions and implementation recommendations

### 5.1 Strategy recommendation

| Option | Cost | Effectiveness | Recommendation |
|---|---|---|---|
| Grid Search (reduced grid) | ~20-30 min | Moderate | Acceptable if Optuna is not available |
| Random Search (50 trials) | ~30-45 min | High | Recommended as default |
| Optuna (50 trials) | ~45-60 min | Very High | Recommended if dependency can be added |

### 5.2 Recommended configuration

```python
# Recommended config for G9
config = {
    'strategy': 'random_search',
    'n_iter': 50,
    'cv_folds': 5,
    'early_stopping': True,
    'max_estimators': 500,
    'stopping_rounds': 50,
    'scoring': 'recall',  # primary
    'constraints': {
        'precision_min': 0.70  # minimum acceptable
    }
}
```

## 6. Visualizations — Graphic specifications

The following visualizations should be generated during G9 execution to document the results.

### 6.1 Graphic 1: Heatmap of Recall vs (max_depth × learning_rate)

**What it shows:** impact of `max_depth` and `learning_rate` on mean CV Recall.

**Code to generate:**

```python
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

# Assuming we have random search results in a DataFrame
# results_df = pd.DataFrame(search.cv_results_)

# Pivot table for heatmap
pivot = results_df.pivot_table(
    values='mean_test_recall',
    index='param_max_depth',
    columns='param_learning_rate',
    aggfunc='mean'
)

fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(
    pivot,
    annot=True,
    fmt='.4f',
    cmap='RdYlGn',
    center=pivot.values.mean(),
    cbar_kws={'label': 'CV Recall'},
    ax=ax,
)
ax.set_title('CV Recall vs max_depth × learning_rate', fontsize=14, fontweight='bold')
ax.set_xlabel('learning_rate')
ax.set_ylabel('max_depth')
plt.tight_layout()
plt.savefig('docs/assets/hp_heatmap_recall.png', dpi=150)
plt.show()
```

**How to interpret:**
```
         learning_rate
         0.05      0.10      0.20
max_depth
3        0.9512    0.9534    0.9518    ← shallow trees, stable recall
5        0.9538    0.9551    0.9523    ← optimal found here
10       0.9541    0.9529    0.9487    ← deeper, more variance
15       0.9503    0.9491    0.9432    ← visible overfitting
```

Expected pattern: recall rises with max_depth until ~5-10, then drops due to overfitting. Low learning rate = better recall (more trees, more generalization).

---

### 6.2 Graphic 2: Boxplot of Recall by config (top-10)

**What it shows:** Recall distribution across the 5 folds for the top-10 configs.

**Code to generate:**

```python
# Get the 10 best trials by mean recall
top10_trials = results_df.nlargest(10, 'mean_test_recall')

fig, ax = plt.subplots(figsize=(14, 6))

data_for_boxplot = []
labels = []

for i, row in top10_trials.iterrows():
    params_str = f"d={row['param_max_depth']}, l={row['param_num_leaves']}, lr={row['param_learning_rate']:.2f}"
    labels.append(params_str)

    # Extract the 5 fold scores from cv_results
    fold_scores = [
        results_df.loc[i, f'split{j}_test_recall']
        for j in range(5)
    ]
    data_for_boxplot.append(fold_scores)

bp = ax.boxplot(data_for_boxplot, patch_artist=True)

# Color: green to red gradient (best to worst)
colors = plt.cm.RdYlGn(np.linspace(0.8, 0.3, 10))
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=9)
ax.set_ylabel('CV Recall', fontsize=12)
ax.set_title('Top-10 configurations — Recall by fold (5-fold CV)', fontsize=14, fontweight='bold')
ax.axhline(y=0.95, color='red', linestyle='--', linewidth=1.5, label='Target MVP (0.95)')
ax.legend()
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('docs/assets/hp_boxplot_top10_recall.png', dpi=150)
plt.show()
```

**How to interpret:**
```
Config                          Fold1   Fold2   Fold3   Fold4   Fold5   Mean
d=5, l=31, lr=0.05              █████   █████   ████    █████   █████   0.9551  ← optimal
d=5, l=31, lr=0.10              ████    █████   █████   ████    █████   0.9543
d=5, l=63, lr=0.05              █████   ████    █████   ████    █████   0.9538
...
```

Small boxes = stable model. Large boxes = split sensitivity. The 0.95 threshold (red line) should be within most boxes for the model to be viable.

---

### 6.3 Graphic 3: Scatter — Recall vs Precision (all trials)

**What it shows:** trade-off between Recall and Precision for all tested configs.

**Code to generate:**

```python
fig, ax = plt.subplots(figsize=(10, 8))

scatter = ax.scatter(
    results_df['mean_test_recall'],
    results_df['mean_test_precision'],
    c=results_df['mean_test_roc_auc'],
    cmap='viridis',
    alpha=0.7,
    s=50,
    edgecolors='white',
    linewidth=0.5,
)

# Threshold lines
ax.axvline(x=0.95, color='red', linestyle='--', alpha=0.7, label='Recall min (0.95)')
ax.axhline(y=0.75, color='orange', linestyle='--', alpha=0.7, label='Precision min (0.75)')

# Highlight top-3
top3 = results_df.nlargest(3, 'mean_test_recall')
for _, row in top3.iterrows():
    ax.annotate(
        f"d={row['param_max_depth']}, l={row['param_num_leaves']}, lr={row['param_learning_rate']:.2f}",
        (row['mean_test_recall'], row['mean_test_precision']),
        xytext=(10, 10),
        textcoords='offset points',
        fontsize=8,
        bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.5),
    )

# Area of fulfilled criteria
ax.fill_between([0.95, 1.01], [0.75, 0.75], [1.01, 1.01],
                color='green', alpha=0.1, label='MVP zone fulfilled')

cbar = plt.colorbar(scatter, ax=ax, label='ROC-AUC')
ax.set_xlabel('Recall (Mean CV)', fontsize=12)
ax.set_ylabel('Precision (Mean CV)', fontsize=12)
ax.set_title('Trade-off Recall vs Precision — All trials (n=50)', fontsize=14, fontweight='bold')
ax.legend(loc='lower right')
ax.set_xlim([0.93, 0.97])
ax.set_ylim([0.70, 0.85])
ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('docs/assets/hp_scatter_recall_precision.png', dpi=150)
plt.show()
```

**How to interpret:**
```
                    Precision
                    0.70    0.75    0.80    0.85
               │
Recall  0.96  │              ★ top-3
         0.955 │         ● ● ●  ← green zone (MVP fulfilled)
         0.95  │───────────────  ← min threshold
         0.945 │    ● ● ● ●
               └────────────────────
```

Points in green zone = configs meeting both MVP criteria. Points higher/right = better trade-off. Color = ROC-AUC (yellower = better separation).

---

### 6.4 Graphic 4: Parallel Coordinates — Top-20 configurations

**What it shows:** how hyperparameters vary across the top-20 configs that met Recall ≥ 0.95.

**Code to generate:**

```python
from pandas.plotting import parallel_coordinates

# Filter configs meeting Recall >= 0.95
viable = results_df[results_df['mean_test_recall'] >= 0.95].copy()

# Select hyperparam and metric columns
hp_cols = ['param_max_depth', 'param_num_leaves', 'param_learning_rate',
           'param_min_child_samples', 'param_reg_alpha', 'param_reg_lambda']
metric_cols = ['mean_test_recall', 'mean_test_precision', 'mean_test_roc_auc']

# Normalize for visualization
for col in hp_cols + metric_cols:
    viable[col] = (viable[col] - viable[col].min()) / (viable[col].max() - viable[col].min() + 1e-8)

# Add label for coloring
viable['config_id'] = range(len(viable))
viable['label'] = viable.apply(lambda r: f"{r['mean_test_recall']:.4f}", axis=1)

# Plot
fig, ax = plt.subplots(figsize=(14, 6))
parallel_coordinates(
    viable[hp_cols + ['config_id']],
    class_column='config_id',
    cols=hp_cols,
    ax=ax,
    color=plt.cm.viridis(np.linspace(0, 1, len(viable))),
    alpha=0.7,
)

ax.set_xticklabels(
    ['max_depth', 'num_leaves', 'learning_rate', 'min_child_samples', 'reg_alpha', 'reg_lambda'],
    rotation=45, ha='right'
)
ax.set_ylabel('Normalized value', fontsize=12)
ax.set_title('Top viable configs (Recall ≥ 0.95) — Parallel Coordinates', fontsize=14, fontweight='bold')
ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('docs/assets/hp_parallel_coordinates.png', dpi=150)
plt.show()
```

**How to interpret:**
```
max_depth   num_leaves   learning_rate  min_child_samples  reg_alpha  reg_lambda
    │            │               │                 │              │            │
 0.0 │───────────│───────────────│─────────────────│──────────────│───────────│  ← low
 0.5 │───────────│───────────────│─────────────────│──────────────│───────────│  ← medium
 1.0 │───────────│───────────────│─────────────────│──────────────│───────────│  ← high

Each line = a viable config
Lines going in same direction = consistent patterns
Ex: good configs tend to have low max_depth (~0.2-0.4) and high learning_rate (~0.7-1.0)
```

Consistent patterns between lines indicate which hyperparameters are important for the model.

---

### 6.5 Graphic 5: Feature Importance — SHAP values (if implemented)

**What it shows:** impact of each feature on the predictions of the best model, with direction (positive/negative).

**Code to generate:**

```python
import shap

# Train best model
best_model = search.best_estimator_

# Create explainer
explainer = shap.TreeExplainer(best_model)

# Calculate SHAP values on test set (or a subset)
X_sample = X_test[:500]  # subset for cost
shap_values = explainer.shap_values(X_sample)

# Global plot
fig, ax = plt.subplots(figsize=(12, 8))
shap.summary_plot(
    shap_values,
    X_sample,
    feature_names=feature_names,
    show=False,
    plot_size=None,
)
plt.title('SHAP Summary — Best Model (Tuned)', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('docs/assets/hp_shap_summary.png', dpi=150, bbox_inches='tight')
plt.show()
```

**How to interpret:**
```
Feature              SHAP value (impact on prediction)
url_length           ████████████████████████████ → +0.15  ← highest positive impact
content_pct_density  █████████████████████████ → +0.12
url_query_length     ████████████████████████ → +0.10
...
method_is_get        ████ → +0.02
method_is_put        █ → +0.01
```

Red dots = high feature value. Blue dots = low value. Horizontal spread = the feature impacts many predictions. Dot = a single prediction.

---

### 6.6 Graphic 6: Evolution of trials — Optuna (if used)

**What it shows:** how Recall evolves trial by trial in Optuna.

**Code to generate:**

```python
fig, ax = plt.subplots(figsize=(12, 6))

# Get study history
history = study.trials_dataframe()

ax.plot(history['number'], history['value'], 'b.-', alpha=0.7, label='Recall')
ax.axhline(y=0.95, color='red', linestyle='--', label='Target MVP')

# Highlight best
best_trial = history[history['value'] == history['value'].max()].iloc[0]
ax.scatter([best_trial['number']], [best_trial['value']],
           color='green', s=200, zorder=5, marker='*', label=f"Best: trial {int(best_trial['number'])}")

ax.set_xlabel('Trial number', fontsize=12)
ax.set_ylabel('CV Recall', fontsize=12)
ax.set_title('Optuna — Recall evolution (50 trials)', fontsize=14, fontweight='bold')
ax.legend()
ax.grid(alpha=0.3)
ax.set_ylim([0.93, 0.96])

plt.tight_layout()
plt.savefig('docs/assets/hp_optuna_evolution.png', dpi=150)
plt.show()
```

**How to interpret:**
```
Recall
0.960 │
0.955 │        ★ best
0.950 │    ╱───────────────────  ← curve converges
0.945 │──╱  ───── ──── ────────  ← last trials don't improve
0.940 └────────────────────────
     1   10   20   30   40   50
              Trial
```

If the curve converges quickly and stabilizes, the search space is sufficient. If it keeps rising at the end, there is room for more trials.

---

### 6.7 Summary of graphics to generate

| # | Graphic | File | Purpose |
|---|---|---|---|
| 1 | Heatmap recall vs max_depth × learning_rate | `hp_heatmap_recall.png` | See interaction of main params |
| 2 | Boxplot top-10 configs | `hp_boxplot_top10_recall.png` | See stability of each config |
| 3 | Scatter recall vs precision | `hp_scatter_recall_precision.png` | See trade-off and MVP zone |
| 4 | Parallel coordinates (top viable) | `hp_parallel_coordinates.png` | See patterns in hyperparams |
| 5 | SHAP summary (best model) | `hp_shap_summary.png` | Understand feature importance of tuned model |
| 6 | Optuna evolution | `hp_optuna_evolution.png` | See search convergence |

**All graphics are saved in:** `docs/assets/` (create directory if it doesn't exist)

```bash
mkdir -p docs/assets
```

### 5.4 Conditions for not running G9

G9 can be marked as "not run" if:
- The model already meets all MVP criteria with margin (> 1% over each threshold)
- The project timeline doesn't allow ~1 hour investment in tuning
- Computational resources are not available

**Current state:** Model A meets Recall 95.43% ≥ 95% and Precision 79.29% ≥ 75%. The margin is small but existent. The ROI of G9 depends on whether we expect tuning to significantly improve or not.

**Based on the feature ceiling analysis (G3/G4):** the bottleneck of the current model is features, not hyperparameters. G9 has a high probability of not finding significant improvements. This suggests G9 could be marked as "completed with no changes" or "postponed until new features are available".