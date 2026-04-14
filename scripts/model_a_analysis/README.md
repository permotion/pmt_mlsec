# Model A — Análisis post-training

Scripts para evaluar y caracterizar el modelo post-training.

## Requisitos

- Modelo descargado desde MLflow (los scripts lo descargan automáticamente)
- Dataset `data/processed/csic2010/features_v4.parquet`
- Variables de entorno: `MLFLOW_TRACKING_URI` (default: `http://localhost:5081`)

## Cómo ejecutar

```bash
cd "/Users/permotion/Desktop/repositories/PERMOTION/PMT MLSec"
source .venv/bin/activate
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/threshold_sweep.py

# 2. Análisis de FP/FN
python fp_analysis.py

# 3. Feature importance
python feature_importance.py

# 4. Feature ablation
python ablation.py
```

## Descripción de scripts

| Script | Qué hace |
|---|---|
| `threshold_sweep.py` | Curva Precision/Recall/F1 vs threshold (0.10–0.80) |
| `fp_analysis.py` | Caracterización de los 938 FP y 300 FN |
| `feature_importance.py` | Gain de cada feature en LightGBM |
| `ablation.py` | Impacto de remover cada grupo de features |