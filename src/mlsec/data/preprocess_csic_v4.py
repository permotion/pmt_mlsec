"""
Preprocessing pipeline — Modelo A (CSIC 2010) — v4

Lee: data/raw/csic2010/csic_database.csv
Escribe: data/processed/csic2010/features_v4.parquet

Cambios respecto a v3 (ver docs/model_a/v6.md):

Agregada en v6 (csic2010_feature_analysis_v6.ipynb):
- content_param_density: content_param_count / content_length.clip(1)
  Densidad de parámetros relativa al tamaño del body.
  Correlación (subpoblación POST): -0.216
  Impacto en v6: FP 943→938 (-5), Precision +0.0007
  Justificación: los POST maliciosos tienen valores más largos (payloads inyectados)
  → menos '=' por carácter de body que los formularios legítimos.

Características:
- content_param_count quedó con importance ~0 en LightGBM (reemplazado por la densidad)
- Se mantiene en el dataset por compatibilidad con análisis anteriores

Decisiones heredadas de v1–v3 (docs/eda.md, docs/model_a/v3.md, docs/model_a/v4.md):
- 11 columnas constantes o sin señal descartadas
- Method → one-hot (method_is_get, method_is_post, method_is_put)
- URL → indicadores de texto percent-encoded (pct27, pct3c, dashdash, script, select)
- content → mismos indicadores en body POST
- content_length = 0 para GETs (no NaN)
- Desbalance leve 59/41 → class_weight='balanced' en el modelo, no SMOTE aquí

Estado final de Modelo A:
- LightGBM v6: Recall 0.9548 ✅ / Precision 0.7928 ❌ / ROC-AUC 0.9661
- Techo práctico identificado: ~0.79 Precision con features de campos HTTP individuales
- Las features Latin-1 (v7) no aportaron señal — ataques CSIC 2010 también tienen Latin-1
- Decisión: aceptar Precision 0.793 como techo y avanzar a Modelo B
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[3]
RAW_PATH = ROOT / "data" / "raw" / "csic2010" / "csic_database.csv"
OUT_DIR  = ROOT / "data" / "processed" / "csic2010"
OUT_PATH = OUT_DIR / "features_v4.parquet"

COLS_TO_DROP = [
    "Unnamed: 0", "User-Agent", "Pragma", "Cache-Control", "Accept",
    "Accept-encoding", "Accept-charset", "language", "content-type",
    "host", "connection", "cookie", "lenght", "content", "URL",
]

TEXT_INDICATORS = {
    "pct27":    "%27",
    "pct3c":    "%3C",
    "dashdash": "--",
    "script":   "script",
    "select":   "SELECT",
}


def build_url_features(df: pd.DataFrame) -> pd.DataFrame:
    url = df["URL"].fillna("")

    # v1/v2
    df["url_length"]      = url.str.len().astype("int32")
    df["url_param_count"] = url.str.count("=").astype("int16")
    df["url_pct_density"] = (url.str.count("%") / url.str.len().clip(lower=1)).astype("float32")

    # v4 — estructura de URL
    url_path  = url.str.split("?").str[0]
    url_query = url.str.split("?").str[1].fillna("")
    df["url_path_depth"]   = url_path.str.count("/").astype("int16")
    df["url_query_length"] = url_query.str.len().astype("int32")
    df["url_has_query"]    = url.str.contains("?", regex=False).astype("int8")

    for name, pattern in TEXT_INDICATORS.items():
        df[f"url_has_{name}"] = url.str.contains(pattern, case=False, regex=False).astype("int8")

    return df


def build_content_features(df: pd.DataFrame) -> pd.DataFrame:
    content = df["content"].fillna("")

    # v1/v2
    df["content_length"] = content.str.len().astype("int32")

    # v3 — densidad de encoding y conteo de parámetros en body
    df["content_pct_density"]  = (content.str.count("%") / content.str.len().clip(lower=1)).astype("float32")
    df["content_param_count"]  = content.str.count("=").astype("int16")

    # v6 — densidad de parámetros relativa al tamaño del body
    df["content_param_density"] = (
        df["content_param_count"] / df["content_length"].clip(lower=1)
    ).astype("float32")

    for name, pattern in TEXT_INDICATORS.items():
        df[f"content_has_{name}"] = content.str.contains(pattern, case=False, regex=False).astype("int8")

    return df


def encode_method(df: pd.DataFrame) -> pd.DataFrame:
    method = df["Method"].str.upper()
    df["method_is_get"]  = (method == "GET").astype("int8")
    df["method_is_post"] = (method == "POST").astype("int8")
    df["method_is_put"]  = (method == "PUT").astype("int8")
    return df


def preprocess(raw_path: Path = RAW_PATH, out_path: Path = OUT_PATH) -> pd.DataFrame:
    print(f"Leyendo {raw_path} ...")
    df = pd.read_csv(raw_path)
    print(f"Shape original: {df.shape}")

    df = df.rename(columns={"classification": "label"})
    df["label"] = df["label"].astype("int8")

    df = build_url_features(df)
    df = build_content_features(df)
    df = encode_method(df)

    cols_present = [c for c in COLS_TO_DROP if c in df.columns]
    df = df.drop(columns=cols_present + ["Method"])

    feature_cols = [
        "method_is_get", "method_is_post", "method_is_put",
        "url_length", "url_param_count", "url_pct_density",
        "url_path_depth", "url_query_length", "url_has_query",
        "url_has_pct27", "url_has_pct3c", "url_has_dashdash",
        "url_has_script", "url_has_select",
        "content_length", "content_pct_density", "content_param_count",
        "content_param_density",
        "content_has_pct27", "content_has_pct3c", "content_has_dashdash",
        "content_has_script", "content_has_select",
        "label",
    ]
    df = df[feature_cols]

    print(f"Shape final: {df.shape}")
    print(f"Features ({len(feature_cols)-1}): {df.drop(columns=['label']).columns.tolist()}")
    print(f"Distribución label:\n{df['label'].value_counts()}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"Guardado en {out_path}")

    return df


if __name__ == "__main__":
    preprocess()
