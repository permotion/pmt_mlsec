"""
Análisis de FP restantes — v6
Objetivo: evaluar si el gap Precision 0.793 → 0.85 es cerrable.

Cruza los FP del test set con el CSV crudo para ver:
- Contenido real de URL y body de los FP
- Columnas de headers descartadas en el EDA (content-type, cookie)
- Si los FP son ruido inherente del dataset o si hay señal pendiente

Reproduce exactamente el split y el modelo de v6 (LightGBM, min_recall_val=0.955).
"""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix, precision_recall_curve, recall_score, precision_score
from lightgbm import LGBMClassifier
import warnings
warnings.filterwarnings("ignore")

ROOT      = Path(__file__).resolve().parents[2]
RAW_PATH  = ROOT / "data" / "raw" / "csic2010" / "csic_database.csv"
FEAT_PATH = ROOT / "data" / "processed" / "csic2010" / "features_v3.parquet"

RANDOM_STATE   = 42
MIN_RECALL_VAL = 0.955


# ── Reproducir modelo v6 ────────────────────────────────────────────────────

def find_threshold(y_true, y_proba, min_recall=MIN_RECALL_VAL):
    precs, recs, thrs = precision_recall_curve(y_true, y_proba)
    mask = recs[:-1] >= min_recall
    if not mask.any():
        return float(thrs[np.argmax(recs[:-1])])
    return float(thrs[np.where(mask, precs[:-1], 0).argmax()])


def build_model_and_fp_indices():
    """Entrena el modelo v6 y devuelve los índices originales de los FP en el test set."""
    df_feat = pd.read_parquet(FEAT_PATH)
    df_feat["content_param_density"] = (
        df_feat["content_param_count"] / df_feat["content_length"].clip(lower=1)
    ).astype("float32")

    feature_cols = [c for c in df_feat.columns if c != "label"]
    X = df_feat[feature_cols].values.astype("float32")
    y = df_feat["label"].values

    X_train, X_temp, y_train, y_temp, idx_train, idx_temp = train_test_split(
        X, y, df_feat.index, test_size=0.30, stratify=y, random_state=RANDOM_STATE
    )
    X_val, X_test, y_val, y_test, idx_val, idx_test = train_test_split(
        X_temp, y_temp, idx_temp, test_size=0.50, stratify=y_temp, random_state=RANDOM_STATE
    )

    continuous_features = ["url_length", "url_query_length", "content_length"]
    continuous_idx = [feature_cols.index(c) for c in continuous_features]
    scaler = StandardScaler()
    X_train[:, continuous_idx] = scaler.fit_transform(X_train[:, continuous_idx])
    X_val[:, continuous_idx]   = scaler.transform(X_val[:, continuous_idx])
    X_test[:, continuous_idx]  = scaler.transform(X_test[:, continuous_idx])

    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    lgbm = LGBMClassifier(
        n_estimators=200, scale_pos_weight=neg / pos,
        random_state=RANDOM_STATE, n_jobs=-1, verbose=-1
    )
    lgbm.fit(X_train, y_train)

    val_proba  = lgbm.predict_proba(X_val)[:, 1]
    threshold  = find_threshold(y_val, val_proba)
    test_proba = lgbm.predict_proba(X_test)[:, 1]
    test_pred  = (test_proba >= threshold).astype(int)

    rc = recall_score(y_test, test_pred)
    pr = precision_score(y_test, test_pred)
    cm = confusion_matrix(y_test, test_pred)
    print(f"Modelo v6 reproducido — threshold={threshold:.4f}")
    print(f"  Recall={rc:.4f}  Precision={pr:.4f}  FP={cm[0,1]}  FN={cm[1,0]}")

    fp_mask      = (y_test == 0) & (test_pred == 1)
    tn_mask      = (y_test == 0) & (test_pred == 0)
    fp_orig_idx  = idx_test[fp_mask]
    tn_orig_idx  = idx_test[tn_mask]
    fp_proba     = test_proba[fp_mask]

    return fp_orig_idx, tn_orig_idx, fp_proba, df_feat, feature_cols


# ── Análisis ─────────────────────────────────────────────────────────────────

def analyze_fp_in_raw_csv(fp_orig_idx, tn_orig_idx, fp_proba):
    print(f"\nCargando CSV crudo: {RAW_PATH}")
    df_raw = pd.read_csv(RAW_PATH)
    print(f"Shape: {df_raw.shape}")
    print(f"Columnas: {df_raw.columns.tolist()}\n")

    fp_raw = df_raw.loc[fp_orig_idx].copy()
    tn_raw = df_raw.loc[tn_orig_idx].copy()
    fp_raw["proba"] = fp_proba

    # ── 1. Distribución de content-type en FP vs TN ──────────────────────────
    if "content-type" in df_raw.columns:
        print("=" * 60)
        print("1. Content-type — FP vs TN")
        print("=" * 60)
        ct_fp = fp_raw["content-type"].value_counts(dropna=False).head(10)
        ct_tn = tn_raw["content-type"].value_counts(dropna=False).head(10)
        print("\nFP content-type:")
        print(ct_fp.to_string())
        print("\nTN content-type:")
        print(ct_tn.to_string())

    # ── 2. Distribución de cookie en FP vs TN ────────────────────────────────
    if "cookie" in df_raw.columns:
        print("\n" + "=" * 60)
        print("2. Cookie — ¿tienen cookie los FP vs TN?")
        print("=" * 60)
        fp_has_cookie = fp_raw["cookie"].notna() & (fp_raw["cookie"] != "")
        tn_has_cookie = tn_raw["cookie"].notna() & (tn_raw["cookie"] != "")
        print(f"  FP con cookie: {fp_has_cookie.sum()} / {len(fp_raw)} ({fp_has_cookie.mean():.1%})")
        print(f"  TN con cookie: {tn_has_cookie.sum()} / {len(tn_raw)} ({tn_has_cookie.mean():.1%})")

    # ── 3. Muestra de FP reales — alta confianza (proba > 0.7) ───────────────
    print("\n" + "=" * 60)
    print("3. FP de alta confianza — URL y content reales")
    print("=" * 60)
    fp_high = fp_raw[fp_raw["proba"] > 0.7].sort_values("proba", ascending=False)
    print(f"FP con proba > 0.70: {len(fp_high)}\n")
    for _, row in fp_high.head(15).iterrows():
        print(f"  proba={row['proba']:.3f}  method={row.get('Method', '?')}")
        print(f"  URL    : {str(row.get('URL', ''))[:120]}")
        content_val = str(row.get('content', ''))
        print(f"  content: {content_val[:120] if content_val != 'nan' else '(vacío)'}")
        if "content-type" in row:
            print(f"  ct     : {row['content-type']}")
        print()

    # ── 4. Muestra de FP reales — baja confianza (cerca del threshold) ───────
    print("=" * 60)
    print("4. FP de baja confianza — proba entre threshold y 0.35")
    print("=" * 60)
    fp_low = fp_raw[fp_raw["proba"] <= 0.35].sort_values("proba")
    print(f"FP con proba ≤ 0.35: {len(fp_low)}\n")
    for _, row in fp_low.head(10).iterrows():
        print(f"  proba={row['proba']:.3f}  method={row.get('Method', '?')}")
        print(f"  URL    : {str(row.get('URL', ''))[:120]}")
        content_val = str(row.get('content', ''))
        print(f"  content: {content_val[:120] if content_val != 'nan' else '(vacío)'}")
        print()

    # ── 5. ¿Son etiquetados correctamente? Comparar con TN similares ─────────
    print("=" * 60)
    print("5. Resumen — ¿son realmente normales estos FP?")
    print("=" * 60)
    # FP con URL que contiene palabras sospechosas pero label=0
    suspicious_keywords = ["%27", "SELECT", "script", "--", "%3C", "OR 1"]
    for kw in suspicious_keywords:
        n_fp_url = fp_raw["URL"].astype(str).str.contains(kw, case=False, regex=False).sum()
        n_fp_con = fp_raw["content"].astype(str).str.contains(kw, case=False, regex=False).sum()
        if n_fp_url > 0 or n_fp_con > 0:
            print(f"  '{kw}' → FP con keyword en URL: {n_fp_url}  en content: {n_fp_con}")

    print("\n  FP sin ningún keyword sospechoso en URL ni content:")
    clean_fp = fp_raw[
        ~fp_raw["URL"].astype(str).str.contains("|".join(suspicious_keywords), case=False, regex=False) &
        ~fp_raw["content"].astype(str).str.contains("|".join(suspicious_keywords), case=False, regex=False)
    ]
    print(f"    {len(clean_fp)} / {len(fp_raw)} ({len(clean_fp)/len(fp_raw):.1%})")
    print("  → Estos son FP estructurales puros: ningún keyword, clasificados por longitud/estructura")

    return fp_raw, tn_raw


if __name__ == "__main__":
    fp_idx, tn_idx, fp_proba, df_feat, feature_cols = build_model_and_fp_indices()
    fp_raw, tn_raw = analyze_fp_in_raw_csv(fp_idx, tn_idx, fp_proba)
