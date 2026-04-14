"""
Feature ablation — impacto de remover grupos de features.
Entrena modelos sin cada grupo y compara Recall/Precision vs baseline.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score
import lightgbm as lgb
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
import requests
import tempfile
import pickle
import mlflow
from mlsec.api.model_loader import THRESHOLD as CALIBRATED_THRESHOLD

# Cargar dataset
df = pd.read_parquet(ROOT / "data/processed/csic2010/features_v4.parquet")
X_df = df.drop(columns=["label"])
feature_names = X_df.columns.tolist()
X_np = X_df.values
y = df["label"].values

# Mismo split que el DAG (70/30) — numpy para ablation, DataFrame para baseline
X_tr, X_val_np, y_tr, y_val = train_test_split(
    X_np, y, test_size=0.3, random_state=42, stratify=y
)
X_val_df = pd.DataFrame(X_val_np, columns=feature_names)

# Descargar modelo desde MLflow (nginx proxy en puerto 5083)
tracking_uri = "http://localhost:5081"
mlflow.set_tracking_uri(tracking_uri)
client = mlflow.tracking.MlflowClient()

exp = client.get_experiment_by_name("mlsec-model-a")
runs = client.search_runs(
    experiment_ids=[exp.experiment_id],
    filter_string="attributes.status = 'FINISHED'",
    order_by=["metrics.test_recall DESC"],
)
run_id = runs[0].info.run_id

artifact_root = "file:///opt/mlflow/artifacts"
artifact_url = artifact_root.replace(artifact_root, "http://localhost:5083")
model_url = f"{artifact_url}/1/{run_id}/artifacts/model/model.pkl"

response = requests.get(model_url, stream=True)
response.raise_for_status()
with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
    f.write(response.content)
    model_path = f.name

with open(model_path, "rb") as f:
    model = pickle.load(f)

print(f"Modelo baseline cargado (run_id={run_id[:8]})")

bl_proba = model.predict_proba(X_val_df)[:, 1]
bl_pred = (bl_proba >= CALIBRATED_THRESHOLD).astype(int)
bl_recall = recall_score(y_val, bl_pred)
bl_precision = precision_score(y_val, bl_pred)
print(f"Baseline (all features): Recall={bl_recall:.4f}  Precision={bl_precision:.4f}  threshold={CALIBRATED_THRESHOLD}")
print()

# Grupos de features por índice en FEATURE_NAMES
# FEATURE_NAMES order:
#  0- 2: method (3)
#  3- 8: url_struct (6)
#  9-13: url_text (5)
# 14-17: content_struct (4)
# 18-22: content_text (5)
groups = {
    "method (3)":        list(range(0, 3)),
    "url_struct (6)":    list(range(3, 9)),
    "url_text (5)":      list(range(9, 14)),
    "content_struct (4)":list(range(14, 18)),
    "content_text (5)":  list(range(18, 23)),
}

print(f"{'Grupo removido':<25} {'Recall':>8}  {'Precision':>10}  {'delta Recall':>12}")
print("-" * 60)

for name, indices in groups.items():
    mask = np.ones(X_tr.shape[1], dtype=bool)
    mask[indices] = False
    X_tr_ab = X_tr[:, mask]
    X_val_ab = X_val_np[:, mask]

    model = lgb.LGBMClassifier(
        n_estimators=200,
        scale_pos_weight=1.44,
        random_state=42,
        verbose=-1,
    )
    model.fit(X_tr_ab, y_tr)
    proba = model.predict_proba(X_val_ab)[:, 1]
    pred = (proba >= CALIBRATED_THRESHOLD).astype(int)
    r = recall_score(y_val, pred)
    p = precision_score(y_val, pred)
    delta_r = r - bl_recall
    print(f"{name:<25} {r:>8.4f}  {p:>10.4f}  {delta_r:>+12.4f}")