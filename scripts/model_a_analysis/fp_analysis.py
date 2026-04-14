"""
Análisis de los Falsos Positivos del Model A.
Caracteriza qué tipo de requests son los 938 FP.
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
from mlsec.api.model_loader import THRESHOLD

# Cargar dataset
df = pd.read_parquet(ROOT / "data/processed/csic2010/features_v4.parquet")
X = df.drop(columns=["label"])
y = df["label"].values
feature_names = X.columns.tolist()

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

print(f"Modelo cargado (run_id={run_id[:8]}). Threshold: {THRESHOLD}")

proba = model.predict_proba(X)[:, 1]
pred = (proba >= THRESHOLD).astype(int)

# FP: predichos como ataque pero son normales
fp_idx = np.where((pred == 1) & (y == 0))[0]
fp_df = df.iloc[fp_idx].copy()
fp_df["proba"] = proba[fp_idx]

print("=== FP distribution by method ===")
method_col = fp_df[["method_is_get", "method_is_post", "method_is_put"]].idxmax(axis=1)
print(method_col.value_counts())

print()
print("=== FP stats ===")
print(f"Total FP: {len(fp_df)}")
print(f"FP con url_has_pct27=1: {fp_df['url_has_pct27'].sum()}")
print(f"FP con url_has_pct3c=1: {fp_df['url_has_pct3c'].sum()}")
print(f"FP con url_has_dashdash=1: {fp_df['url_has_dashdash'].sum()}")
print(f"FP con url_has_script=1: {fp_df['url_has_script'].sum()}")
print(f"FP con url_has_select=1: {fp_df['url_has_select'].sum()}")
print(f"FP con content_length>0: {(fp_df['content_length']>0).sum()}")
print(f"FP url_length mean: {fp_df['url_length'].mean():.1f}")
print(f"FP url_length std: {fp_df['url_length'].std():.1f}")
print(f"FP proba min: {fp_df['proba'].min():.4f}")
print(f"FP proba max: {fp_df['proba'].max():.4f}")
print(f"FP proba median: {fp_df['proba'].median():.4f}")

print()
print("=== FP proba distribution ===")
buckets = [(0.29, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
for lo, hi in buckets:
    count = ((fp_df["proba"] >= lo) & (fp_df["proba"] < hi)).sum()
    print(f"  [{lo:.2f}, {hi:.2f}): {count}")

# FN: predichos como normales pero son ataques
fn_idx = np.where((pred == 0) & (y == 1))[0]
fn_df = df.iloc[fn_idx].copy()
fn_df["proba"] = proba[fn_idx]

print()
print("=== FN stats ===")
print(f"Total FN: {len(fn_df)}")
print(f"FN url_length mean: {fn_df['url_length'].mean():.1f}")
print(f"FN proba min/max: {fn_df['proba'].min():.4f} / {fn_df['proba'].max():.4f}")