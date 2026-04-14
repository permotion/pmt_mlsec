"""
Feature importance (gain) para Model A.
Imprime todas las features ordenadas por importancia.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import numpy as np
import requests
import tempfile
import pickle
import mlflow

# Cargar dataset para tener feature names
df = pd.read_parquet(ROOT / "data/processed/csic2010/features_v4.parquet")
feature_names = df.drop(columns=["label"]).columns.tolist()

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

print(f"Modelo cargado (run_id={run_id[:8]})")

# Feature importance
importances = model.feature_importances_
sorted_idx = np.argsort(importances)[::-1]

print("=== Feature importance (gain) ===")
for i in sorted_idx:
    bar = "█" * int(importances[i] / importances[sorted_idx[0]] * 30)
    print(f"{feature_names[i]:<30} {importances[i]:>6.1f}  {bar}")