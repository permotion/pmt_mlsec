"""
Preprocessing pipeline — Modelo A (CSIC 2010)

Lee: data/raw/csic2010/csic_database.csv
Escribe: data/processed/csic2010/features.parquet

Decisiones tomadas en el EDA (docs/eda.md):
- 11 columnas constantes o sin señal descartadas
- Method → one-hot (method_is_get, method_is_post, method_is_put)
- URL → indicadores de texto percent-encoded (pct27, pct3c, dashdash, script, select)
- content → mismos indicadores en body POST
- content_length = 0 para GETs (no NaN)
- Desbalance leve 59/41 → class_weight='balanced' en el modelo, no SMOTE aquí
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Rutas relativas a la raíz del repo
ROOT = Path(__file__).resolve().parents[3]
RAW_PATH = ROOT / "data" / "raw" / "csic2010" / "csic_database.csv"
OUT_DIR = ROOT / "data" / "processed" / "csic2010"
OUT_PATH = OUT_DIR / "features.parquet"

# Columnas a descartar — constantes o sin señal (ver docs/eda.md)
COLS_TO_DROP = [
    "Unnamed: 0",
    "User-Agent",
    "Pragma",
    "Cache-Control",
    "Accept",
    "Accept-encoding",
    "Accept-charset",
    "language",
    "content-type",
    "host",
    "connection",
    "cookie",       # identificador de sesión — no aporta señal de ataque
    "lenght",       # reemplazado por content_length engineered
    "content",      # reemplazado por indicadores binarios
    "URL",          # reemplazada por indicadores binarios + url_length
]

# Indicadores de texto a buscar (percent-encoded — chars literales nunca aparecen)
TEXT_INDICATORS = {
    "pct27":    "%27",      # ' (SQLi)
    "pct3c":    "%3C",      # < (XSS)
    "dashdash": "--",       # comentario SQL
    "script":   "script",  # keyword XSS
    "select":   "SELECT",  # keyword SQL
}


def build_url_features(df: pd.DataFrame) -> pd.DataFrame:
    """Construye features a partir de la columna URL."""
    url = df["URL"].fillna("")
    df["url_length"] = url.str.len().astype("int32")
    for name, pattern in TEXT_INDICATORS.items():
        df[f"url_has_{name}"] = url.str.contains(pattern, case=False, regex=False).astype("int8")
    return df


def build_content_features(df: pd.DataFrame) -> pd.DataFrame:
    """Construye features a partir del body (content) — solo relevante en POSTs."""
    content = df["content"].fillna("")
    df["content_length"] = content.str.len().astype("int32")
    for name, pattern in TEXT_INDICATORS.items():
        df[f"content_has_{name}"] = content.str.contains(pattern, case=False, regex=False).astype("int8")
    return df


def encode_method(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot encoding de Method → method_is_get, method_is_post, method_is_put."""
    method = df["Method"].str.upper()
    df["method_is_get"]  = (method == "GET").astype("int8")
    df["method_is_post"] = (method == "POST").astype("int8")
    df["method_is_put"]  = (method == "PUT").astype("int8")
    return df


def preprocess(raw_path: Path = RAW_PATH, out_path: Path = OUT_PATH) -> pd.DataFrame:
    print(f"Leyendo {raw_path} ...")
    df = pd.read_csv(raw_path)
    print(f"Shape original: {df.shape}")

    # Label
    df = df.rename(columns={"classification": "label"})
    df["label"] = df["label"].astype("int8")

    # Feature engineering
    df = build_url_features(df)
    df = build_content_features(df)
    df = encode_method(df)

    # Descartar columnas crudas
    cols_present = [c for c in COLS_TO_DROP if c in df.columns]
    df = df.drop(columns=cols_present + ["Method"])

    # Columnas finales
    feature_cols = [
        "method_is_get", "method_is_post", "method_is_put",
        "url_length",
        "url_has_pct27", "url_has_pct3c", "url_has_dashdash",
        "url_has_script", "url_has_select",
        "content_length",
        "content_has_pct27", "content_has_pct3c", "content_has_dashdash",
        "content_has_script", "content_has_select",
        "label",
    ]
    df = df[feature_cols]

    print(f"Shape final: {df.shape}")
    print(f"Distribución label:\n{df['label'].value_counts()}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"Guardado en {out_path}")

    return df


if __name__ == "__main__":
    preprocess()
