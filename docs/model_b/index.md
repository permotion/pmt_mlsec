# Modelo B — Network Attack Detection

**Dataset:** UNSW-NB15  
**Input:** Features de flujo de red  
**Output:** `0` benign / `1` malicious

---

## Criterios de éxito MVP

| Métrica | Mínimo |
|---|---|
| F1 | ≥ 0.88 |
| ROC-AUC | ≥ 0.95 |

---

## Estado actual

!!! info "Pendiente"
    El Modelo B está en cola. El preprocessing está listo (`preprocess_unsw.py`), pero el entrenamiento y los experimentos todavía no comenzaron.

    **Pendiente:** crear `src/mlsec/models/train_model_b.py` y ejecutar el baseline.

---

## Preprocessing completado

**Script:** `src/mlsec/data/preprocess_unsw.py`  
**Outputs:** `data/processed/unsw_nb15/train.parquet` (175.341 × 62), `test.parquet` (82.332 × 62)

Decisiones clave del preprocessing:

| Decisión | Justificación |
|---|---|
| Scaler: **RobustScaler** | Resistente a outliers — `sbytes` max 12M, `sload` max 5.9B |
| Drop `dwin`, `dloss`, `is_sm_ips_ports` | Redundantes con otras features |
| Drop `attack_cat` | Solo para análisis — no es un feature de entrada |
| `proto`: top-10 + 'other' one-hot | 133 valores únicos — reducción necesaria |
| `service`, `state`: one-hot directo | Pocos valores únicos |
| `DataFrame.align()` | Sincroniza columnas train/test tras one-hot |

Ver EDA: `notebooks/eda/unsw_nb15_eda.ipynb`
