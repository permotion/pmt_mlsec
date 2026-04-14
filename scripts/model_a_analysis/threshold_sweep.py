"""
Threshold sweep — Precision/Recall vs threshold para Model A.
Imprime CSV con columnas: threshold,precision,recall,f1,fp,fn
"""
import sys
from pathlib import Path

# Agregar src/ al path ANTES de cualquier import de mlsec
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import numpy as np
import requests
import tempfile
import pickle
from mlsec.api.model_loader import THRESHOLD as CALIBRATED_THRESHOLD

# Cargar dataset
df = pd.read_parquet(ROOT / "data/processed/csic2010/features_v4.parquet")

# Mismo split que el DAG (70/30 stratified)
from sklearn.model_selection import train_test_split

X_df = df.drop(columns=["label"])
feature_names = X_df.columns.tolist()
X_np = X_df.values
y = df["label"].values
X_val_np, _, y_val, _ = train_test_split(X_np, y, test_size=0.3, random_state=42, stratify=y)
X_val = pd.DataFrame(X_val_np, columns=feature_names)
print(f"Validation set: {len(y_val)} samples ({y_val.sum()} attacks, {len(y_val)-y_val.sum()} normal)")

# Descargar modelo directo desde MLflow via REST API (funciona desde el host)
tracking_uri = "http://localhost:5081"
exp_name = "mlsec-model-a"

import mlflow
mlflow.set_tracking_uri(tracking_uri)
client = mlflow.tracking.MlflowClient()

exp = client.get_experiment_by_name(exp_name)
runs = client.search_runs(
    experiment_ids=[exp.experiment_id],
    filter_string="attributes.status = 'FINISHED'",
    order_by=["metrics.test_recall DESC"],
)
run = runs[0]
run_id = run.info.run_id

# Descargar desde nginx (proxy de artefactos en puerto 5083)
# El artifact_uri de MLflow es file:///opt/mlflow/artifacts/1/{run_id}/artifacts
# que dentro del contenedor mlflow apunta al volumen mlflow-artifacts.
# Ese volumen está expuesto por nginx en puerto 5083.
artifact_root = "file:///opt/mlflow/artifacts"
artifact_uri = f"{artifact_root}/1/{run_id}/artifacts"
artifact_url = artifact_uri.replace(artifact_root, "http://localhost:5083")
model_url = f"{artifact_url}/model/model.pkl"
print(f"Descargando artefacto: {model_url}")

response = requests.get(model_url, stream=True)
response.raise_for_status()

with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
    f.write(response.content)
    model_path = f.name

with open(model_path, "rb") as f:
    model = pickle.load(f)

threshold = CALIBRATED_THRESHOLD
print(f"Modelo cargado (run_id={run_id[:8]}). Threshold: {threshold}")

# Predecir probabilidades sobre validation set
proba = model.predict_proba(X_val)[:, 1]

# Threshold sweep
print("threshold,precision,recall,f1,fp,fn")
for t in np.arange(0.10, 0.80, 0.02):
    pred = (proba >= t).astype(int)
    tp = ((pred == 1) & (y_val == 1)).sum()
    fp = ((pred == 1) & (y_val == 0)).sum()
    fn = ((pred == 0) & (y_val == 1)).sum()
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    print(f"{t:.2f},{precision:.4f},{recall:.4f},{f1:.4f},{fp},{fn}")