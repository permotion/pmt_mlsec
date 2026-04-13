"""
DAG — Modelo A (CSIC 2010) — Web Attack Detection

Pipeline:
    verify_data → preprocess → train → evaluate

Cada tarea corre con el intérprete de .venv (scikit-learn, LightGBM, MLflow).
Airflow actúa como orquestador — no necesita las librerías de ML instaladas.

Trigger: manual (schedule=None)
"""

from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

ROOT     = Path(__file__).resolve().parents[1]
PYTHON   = ROOT / ".venv" / "bin" / "python"
DATA_RAW = ROOT / "data" / "raw" / "csic2010" / "csic_database.csv"
DATA_OUT = ROOT / "data" / "processed" / "csic2010" / "features_v4.parquet"

PREPROCESS_SCRIPT = ROOT / "src" / "mlsec" / "data" / "preprocess_csic_v4.py"
TRAIN_SCRIPT      = ROOT / "src" / "mlsec" / "models" / "train_model_a_pipeline.py"


def check_raw_data():
    if not DATA_RAW.exists():
        raise FileNotFoundError(
            f"Dataset crudo no encontrado: {DATA_RAW}\n"
            "Descargá el dataset CSIC 2010 y colocalo en data/raw/csic2010/"
        )
    size_mb = DATA_RAW.stat().st_size / 1024 / 1024
    print(f"Dataset encontrado: {DATA_RAW} ({size_mb:.1f} MB)")


with DAG(
    dag_id="dag_model_a",
    description="Modelo A — Web Attack Detection (CSIC 2010)",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["model-a", "csic2010"],
) as dag:

    verify_data = PythonOperator(
        task_id="verify_data",
        python_callable=check_raw_data,
    )

    preprocess = BashOperator(
        task_id="preprocess",
        bash_command=f"{PYTHON} {PREPROCESS_SCRIPT}",
    )

    train = BashOperator(
        task_id="train",
        bash_command=f"{PYTHON} {TRAIN_SCRIPT} --features {DATA_OUT} --min-recall 0.955",
    )

    evaluate = BashOperator(
        task_id="evaluate",
        bash_command=(
            f"{PYTHON} -c \""
            f"import pandas as pd, sys; "
            f"path = '{DATA_OUT}'; "
            f"df = pd.read_parquet(path); "
            f"print(f'Features_v4 generado: {{df.shape[0]}} rows, {{df.shape[1]-1}} features'); "
            f"print('Pipeline completado exitosamente.')"
            f"\""
        ),
    )

    verify_data >> preprocess >> train >> evaluate
