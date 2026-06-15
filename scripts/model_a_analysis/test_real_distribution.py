"""
Test de distribución real — G5 (distribución 41% vs ~1%)

Simula cómo se comportaría el modelo en producción donde el ratio
de ataques es ~1% (99:1 normal:ataque) en lugar del 41% del dataset.

Uso:
    python scripts/model_a_analysis/test_real_distribution.py

Este script:
1. Carga el test set (split 15% del dataset original)
2. Resamplea para ratio 99:1
3. Evalúa con threshold actual (0.3002)
4. Calcula threshold corregido para Recall >= 0.95 en 99:1
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import (
    recall_score,
    precision_score,
    roc_auc_score,
    confusion_matrix,
    precision_recall_curve,
)

# ---------------------------------------------------------------------------
# Cargar dataset y modelo
# ---------------------------------------------------------------------------
df = pd.read_parquet(ROOT / "data/processed/csic2010/features_v4.parquet")
X = df.drop(columns=["label"]).values.astype("float32")
y = df["label"].values
feature_names = df.drop(columns=["label"]).columns.tolist()

# Split igual que en training (70/15/15)
from sklearn.model_selection import train_test_split

X_train, X_temp, y_train, y_temp = train_test_split(
    X, y, test_size=0.30, stratify=y, random_state=42
)
X_val, X_test, y_val, y_test = train_test_split(
    X_temp, y_temp, test_size=0.50, stratify=y_temp, random_state=42
)

# Entrenar modelo igual que pipeline original
neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
spw = neg / pos
model = LGBMClassifier(n_estimators=200, scale_pos_weight=spw, random_state=42, verbose=-1, n_jobs=-1)
model.fit(X_train, y_train)

# Calibrar threshold en val (igual que pipeline)
val_proba = model.predict_proba(X_val)[:, 1]
precisions, recalls, thresholds = precision_recall_curve(y_val, val_proba)
mask = recalls[:-1] >= 0.955
best_idx = np.where(mask, precisions[:-1], 0).argmax()
threshold_dataset = float(thresholds[best_idx])

test_proba = model.predict_proba(X_test)[:, 1]

print("=" * 60)
print("TEST REAL DISTRIBUTION — G5")
print("=" * 60)

# ---------------------------------------------------------------------------
# Evaluación ORIGINAL (41% ataques — mismo dataset)
# ---------------------------------------------------------------------------
pred_41 = (test_proba >= threshold_dataset).astype(int)
recall_41 = recall_score(y_test, pred_41)
precision_41 = precision_score(y_test, pred_41)
cm_41 = confusion_matrix(y_test, pred_41)
fp_41 = int(cm_41[0, 1])
fn_41 = int(cm_41[1, 0])
tn_41 = int(cm_41[0, 0])
tp_41 = int(cm_41[1, 1])

print(f"\n--- Test set ORIGINAL (41% ataques) ---")
print(f"Threshold:     {threshold_dataset:.4f}")
print(f"Recall:        {recall_41:.4f}")
print(f"Precision:     {precision_41:.4f}")
print(f"TP: {tp_41:5d}  TN: {tn_41:5d}  FP: {fp_41:5d}  FN: {fn_41:5d}")
print(f"FP rate:       {fp_41 / (fp_41 + tn_41):.4f}")

# ---------------------------------------------------------------------------
# Evaluación con DISTRIBUCION 99:1
# ---------------------------------------------------------------------------
# Separar por clase
idx_normal = np.where(y_test == 0)[0]
idx_attack = np.where(y_test == 1)[0]

n_normal = len(idx_normal)
# 1% ataques = muestrear 2% de los ataques originales (para mantener proporciones en test)
# Total 99:1 significa 99 normal por 1 attack
# Tenemos ~5400 normales y ~3760 ataques en test
# Para 99:1 → necesitamos ~5400 normales y ~54 ataques
n_attacks_sample = min(len(idx_attack), int(n_normal * 0.0101))  # ~54 ataques

np.random.seed(42)
idx_attack_sampled = np.random.choice(idx_attack, size=n_attacks_sample, replace=False)
idx_normal_sampled = np.random.choice(idx_normal, size=min(n_normal, n_attacks_sample * 99), replace=False)

# Crear test set 99:1
idx_99 = np.concatenate([idx_attack_sampled, idx_normal_sampled])
np.random.shuffle(idx_99)
X_99 = X_test[idx_99]
y_99 = y_test[idx_99]

proba_99 = model.predict_proba(X_99)[:, 1]

# Evaluar con threshold del dataset
pred_99 = (proba_99 >= threshold_dataset).astype(int)

# Métricas 99:1
recall_99 = recall_score(y_99, pred_99) if pred_99.sum() > 0 else 0
precision_99 = precision_score(y_99, pred_99) if pred_99.sum() > 0 else 0
cm_99 = confusion_matrix(y_99, pred_99)
fp_99 = int(cm_99[0, 1])
tn_99 = int(cm_99[0, 0])
fn_99 = int(cm_99[1, 0])
tp_99 = int(cm_99[1, 1])

print(f"\n--- Test set 99:1 ({len(y_99)} samples, {y_99.mean():.1%} ataques) ---")
print(f"Threshold:     {threshold_dataset:.4f}")
print(f"Recall:        {recall_99:.4f}")
print(f"Precision:     {precision_99:.4f}")
print(f"TP: {tp_99:5d}  TN: {tn_99:5d}  FP: {fp_99:5d}  FN: {fn_99:5d}")
fp_rate_99 = fp_99 / (fp_99 + tn_99) if (fp_99 + tn_99) > 0 else 0
print(f"FP rate (99:1): {fp_rate_99:.4f}")

# ---------------------------------------------------------------------------
# Calcular threshold corregido para 99:1
# ---------------------------------------------------------------------------
# Buscar threshold que dé Recall >= 0.95 en distribución 99:1
prec_99, rec_99, th_99 = precision_recall_curve(y_99, proba_99)

# Buscar threshold mínimo que mantenga recall >= 0.95
candidates_95 = np.where(rec_99[:-1] >= 0.95)[0]
if candidates_95.any():
    # De esos, elegir el que maximiza precision
    best_idx_99 = candidates_95[np.argmax(prec_99[:-1][candidates_95])]
    threshold_corrected = float(th_99[best_idx_99])
else:
    # Si ningún threshold da recall 0.95, usar el mínimo que maximise recall
    best_idx_99 = np.argmax(rec_99[:-1])
    threshold_corrected = float(th_99[best_idx_99])

# Evaluar con threshold corregido
pred_99_corrected = (proba_99 >= threshold_corrected).astype(int)
recall_99_corr = recall_score(y_99, pred_99_corrected)
precision_99_corr = precision_score(y_99, pred_99_corrected)
cm_99_corr = confusion_matrix(y_99, pred_99_corrected)
fp_99_corr = int(cm_99_corr[0, 1])

print(f"\n--- Threshold corregido para 99:1 ---")
print(f"Threshold dataset:   {threshold_dataset:.4f}")
print(f"Threshold corregido: {threshold_corrected:.4f}")
print(f"Gap:                 {threshold_corrected - threshold_dataset:+.4f}")
print(f"Recall (corregido):  {recall_99_corr:.4f}")
print(f"Precision (corregido): {precision_99_corr:.4f}")
print(f"FP rate (corregido):  {fp_99_corr / (fp_99_corr + tn_99):.4f}")

# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print("RESUMEN")
print(f"{'=' * 60}")
print(f"Threshold dataset (41% ataques): {threshold_dataset:.4f}")
print(f"Threshold producción (99:1):     {threshold_corrected:.4f}")
print(f"Gap: {threshold_corrected - threshold_dataset:+.4f}")
print()
print(f"FP rate con threshold dataset en 99:1: {fp_rate_99:.4f}")
print(f"FP rate con threshold corregido en 99:1: {fp_99_corr / (fp_99_corr + tn_99):.4f}")
print()
if threshold_corrected - threshold_dataset > 0.05:
    print("⚠️  Umbral sube significativamente — considerar recalibrar para producción")
elif abs(threshold_corrected - threshold_dataset) <= 0.05:
    print("✅ Threshold robusto — diferencia < 0.05")