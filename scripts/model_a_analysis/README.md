# Model A — Post-training analysis

Scripts to evaluate and characterize the model post-training.

## Requirements

- Model downloaded from MLflow (scripts download it automatically)
- Dataset `data/processed/csic2010/features_v4.parquet`
- Environment variables: `MLFLOW_TRACKING_URI` (default: `http://localhost:5081`)

## How to run

```bash
cd "/Users/permotion/Desktop/repositories/PERMOTION/PMT MLSec"
source .venv/bin/activate
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/threshold_sweep.py

# 2. FP/FN analysis
python fp_analysis.py

# 3. Feature importance
python feature_importance.py

# 4. Feature ablation
python ablation.py
```

## Script descriptions

| Script | What it does |
|---|---|
| `threshold_sweep.py` | Precision/Recall/F1 curve vs threshold (0.10–0.80) |
| `fp_analysis.py` | Characterization of the 938 FPs and 300 FNs |
| `feature_importance.py` | Gain of each feature in LightGBM |
| `ablation.py` | Impact of removing each feature group |