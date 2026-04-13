"""
Preprocessing pipeline — Modelo B (UNSW-NB15)

Lee:
  data/raw/unsw_nb15/UNSW_NB15_training-set.parquet
  data/raw/unsw_nb15/UNSW_NB15_testing-set.parquet

Escribe:
  data/processed/unsw_nb15/train.parquet
  data/processed/unsw_nb15/test.parquet

Decisiones tomadas en el EDA (docs/eda.md):
- Split predefinido en parquet — no modificar
- attack_cat descartada — usamos label binario
- dwin, dloss, is_sm_ips_ports descartadas — redundantes (correlación > 0.9)
- proto: top-10 más frecuentes + categoría 'other' → one-hot
- service, state: one-hot directo
- features numéricas: RobustScaler (outliers extremos en sbytes, sload, dload)
- Desbalance 68/32 → class_weight='balanced' en el modelo, no SMOTE aquí
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import RobustScaler

ROOT = Path(__file__).resolve().parents[3]
TRAIN_RAW = ROOT / "data" / "raw" / "unsw_nb15" / "UNSW_NB15_training-set.parquet"
TEST_RAW  = ROOT / "data" / "raw" / "unsw_nb15" / "UNSW_NB15_testing-set.parquet"
OUT_DIR   = ROOT / "data" / "processed" / "unsw_nb15"

# Columnas a descartar
COLS_TO_DROP = [
    "attack_cat",       # solo para análisis — no va como input al modelo
    "dwin",             # 0.99 correlación con swin — redundante
    "dloss",            # 0.98 correlación con dpkts — redundante
    "is_sm_ips_ports",  # 0.94 correlación con sinpkt — redundante
]

CATEGORICAL_COLS = ["proto", "service", "state"]
PROTO_TOP_N = 10  # top-N protocolos + 'other'


def reduce_proto_cardinality(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reduce proto de 133 valores a top-10 + 'other'. Fit en train, transform en ambos."""
    top_proto = train["proto"].value_counts().head(PROTO_TOP_N).index.tolist()
    for df in [train, test]:
        df["proto"] = df["proto"].astype(str).where(
            df["proto"].astype(str).isin(top_proto), other="other"
        )
    return train, test


def encode_categoricals(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One-hot encoding de proto, service, state. Fit en train, align en test."""
    train = pd.get_dummies(train, columns=CATEGORICAL_COLS, dtype="int8")
    test  = pd.get_dummies(test,  columns=CATEGORICAL_COLS, dtype="int8")
    # Alinear columnas — test puede tener categorías que no están en train
    train, test = train.align(test, join="left", axis=1, fill_value=0)
    return train, test


def scale_numerics(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """RobustScaler sobre features numéricas continuas. Fit en train, transform en ambos."""
    # Excluir label y columnas one-hot (int8 ya procesadas)
    num_cols = train.select_dtypes(include=[np.float32, np.float64, np.int16, np.int32, np.int64]).columns.tolist()
    num_cols = [c for c in num_cols if c != "label"]

    scaler = RobustScaler()
    train[num_cols] = scaler.fit_transform(train[num_cols]).astype("float32")
    test[num_cols]  = scaler.transform(test[num_cols]).astype("float32")

    return train, test


def preprocess(
    train_path: Path = TRAIN_RAW,
    test_path: Path  = TEST_RAW,
    out_dir: Path    = OUT_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    print(f"Leyendo train: {train_path}")
    train = pd.read_parquet(train_path)
    print(f"Leyendo test:  {test_path}")
    test  = pd.read_parquet(test_path)

    print(f"Shape original — train: {train.shape} / test: {test.shape}")

    # Label
    train["label"] = train["label"].astype("int8")
    test["label"]  = test["label"].astype("int8")

    # Descartar columnas
    train = train.drop(columns=[c for c in COLS_TO_DROP if c in train.columns])
    test  = test.drop(columns=[c for c in COLS_TO_DROP if c in test.columns])

    # proto: reducir cardinalidad antes de one-hot
    train, test = reduce_proto_cardinality(train, test)

    # Encoding categóricas
    train, test = encode_categoricals(train, test)

    # Escalar numéricas (fit solo en train)
    train, test = scale_numerics(train, test)

    print(f"Shape final — train: {train.shape} / test: {test.shape}")
    print(f"Distribución label train:\n{train['label'].value_counts()}")

    out_dir.mkdir(parents=True, exist_ok=True)
    train.to_parquet(out_dir / "train.parquet", index=False)
    test.to_parquet(out_dir / "test.parquet", index=False)
    print(f"Guardado en {out_dir}")

    return train, test


if __name__ == "__main__":
    preprocess()
