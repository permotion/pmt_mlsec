# Brief — PMT MLSec

Resumen del estado del proyecto, decisiones clave y aprendizajes. Actualizado al 2026-04-13.

---

## Qué es esto

Sistema de detección de ataques con Machine Learning. MVP con dos modelos de clasificación binaria:

| Modelo | Input | Dataset | Target | Estado |
|---|---|---|---|---|
| A — Web Attack Detection | Features de request HTTP | CSIC 2010 (61.065 req) | Recall ≥ 0.95, Precision ≥ 0.85 | ✅ concluido |
| B — Network Attack Detection | Features de flujo de red | UNSW-NB15 (257K flujos) | F1 ≥ 0.88, ROC-AUC ≥ 0.95 | 🔄 en progreso |

Detección **offline** en el MVP — no hay bloqueo en tiempo real.

---

## Modelo A — CSIC 2010 (concluido)

### Punto de partida

El dataset CSIC 2010 tiene 61.065 requests HTTP de una tienda española. 59% normales / 41% ataques (SQLi, XSS, buffer overflow, parameter tampering). Los ataques siempre usan URL encoding — nunca caracteres literales.

Baseline: 4 modelos (LR, RF, XGBoost, LightGBM) con 15 features del EDA. El modelo alcanzó Recall 0.95 fácilmente pero Precision quedó en 0.655 — demasiados falsos positivos.

### Progresión de métricas

| Versión | ROC-AUC | Recall | Precision | FP | Estado |
|---|---|---|---|---|---|
| Baseline | 0.939 | 0.951 | 0.655 | 1886 | ❌ |
| v2 — url_pct_density + url_param_count | 0.950 | 0.950 | 0.704 | 1504 | ❌ |
| v3 — content_pct_density + MLflow | 0.955 | 0.952 | 0.713 | 1444 | ❌ |
| v4 — url_path_depth, url_query_length, url_has_query | 0.966 | 0.949 | 0.803 | 877 | ❌ |
| v5 — Calibración threshold (min_recall_val=0.955) | 0.966 | 0.956 ✅ | 0.792 | 943 | ❌ |
| v6 — content_param_density | 0.966 | 0.955 ✅ | 0.793 | 938 | ❌ |
| v7 — Latin-1 features (no incorporadas) | 0.968 | 0.953 ✅ | 0.793 | 936 | ❌ |
| **Target** | — | **0.95** | **0.85** | ~630 | — |

### Los 4 problemas que se resolvieron

**Problema 1 — Techo de ROC-AUC 0.94 (Baseline → v1)**

El baseline LightGBM llegó a ROC-AUC 0.939 y no mejoraba. El diagnóstico fue que el límite no era el algoritmo sino las features. Análisis de feature importance + análisis de los 1.886 FP identificó que el modelo no tenía información sobre la densidad de encoding en la URL. Las features `url_pct_density` y `url_param_count` subieron ROC-AUC a 0.950 y Precision a 0.704 (-382 FP).

**Problema 2 — Cuerpo POST sin features (v3 → v4)**

Los ataques POST tenían body con encoding denso pero el modelo solo tenía `content_length`. Se agregaron `content_pct_density` y `content_param_count` para el body, y luego las features de estructura de URL (`url_path_depth`, `url_query_length`, `url_has_query`) para el GET. v4 produjo el mayor salto del proyecto: Precision 0.713 → 0.803 (+0.090), FP -567, y rompió el techo de ROC-AUC por primera vez (0.955 → 0.966).

**Problema 3 — Recall bajo threshold fijo (v4 → v5)**

Con el threshold por defecto (0.5), LightGBM v4 tenía Recall 0.9492 — por debajo del mínimo 0.95. El threshold 0.5 no tiene ningún fundamento en este problema: el modelo tiene 41% de positivos, no 50%. Se implementó un sweep de `min_recall_val` (0.950 → 0.985) que optimiza el threshold en validation buscando el que maximiza Precision manteniendo Recall ≥ target. El valor óptimo fue `min_recall_val=0.955` → threshold calibrado 0.2573 → Recall test 0.9556 ✅.

**Problema 4 — Root cause de los FP: confusión de encoding (v6)**

Con 938 FP después de v5, se inspeccionó el CSV crudo. Los FP de alta confianza (proba > 0.70) eran todos formularios legítimos de la tienda española con nombres como `Murgu%EDa`, `lIMpi%24a%FA%F1as`. El modelo los confundía con ataques porque `content_pct_density` cuenta todos los `%XX` por igual — `%F1` (ñ) produce la misma señal que `%27` (SQLi). Los headers `cookie` y `content-type` fueron descartados como señal: el 100% de los requests tienen cookie y content-type es idéntico entre FP y TN del mismo método.

### El problema que no se pudo resolver

**La hipótesis Latin-1 falló (v7)**

La hipótesis era: los ataques nunca usan Latin-1 (no hay razón para encodear ñ en un payload SQL), así que `content_pct_latin1_density` discriminaría FP de TN. La hipótesis era técnicamente correcta para ataques reales — pero CSIC 2010 tiene un quirk: el generador de ataques construye requests contra una tienda española e incluye nombres de campo en español con caracteres acentuados. El body de un ataque POST típico es `apellidos=Garc%EDa&pass=%27+OR+1%3D1--` — el payload de inyección está en el valor de `pass`, pero el nombre del campo `apellidos` tiene `%ED` (í). Distribución prácticamente idéntica: media normal 0.00420 vs ataque 0.00413. Correlación POST: -0.004. Impacto: -2 FP.

### Techo práctico y decisión

Después de v5, v6 y v7, el patrón es claro: los 936 FP son requests normales que el modelo no puede diferenciar de ataques con las dimensiones disponibles de campos HTTP individuales.

| Dimensión analizada | Resultado |
|---|---|
| Longitud y estructura de URL/body | Agotado desde v4 |
| Indicadores de keywords (`%27`, `SELECT`) | 98.6% de FP sin ninguno |
| Estructura de query string | Agotado desde v4 |
| Densidad de parámetros (`content_param_density`) | Señal real pero marginal (-5 FP) |
| Encoding Latin-1 | Sin separación — ataques también tienen Latin-1 |
| Headers HTTP (cookie, content-type) | Sin señal — constantes en el dataset |

**Decisión:** aceptar Precision ~0.793 como techo práctico y avanzar a Modelo B. El gap de 0.057 para llegar a 0.85 requeriría parseo semántico de valores de parámetros (distinguir `key=valor_normal` de `key=%27OR1%3D1`) o features de sesión — un cambio de enfoque, no más feature engineering sobre campos HTTP.

Precision 0.793 con Recall 0.953 es un punto de partida válido para producción con revisión manual de alarmas. Con 936 FP, la tasa de falsa alarma es manejable en un sistema de detección offline.

### Estado del código

```
src/mlsec/data/
├── preprocess_csic_v1.py   → features.parquet      (15 features)
├── preprocess_csic_v2.py   → features_v2.parquet   (17 features)
├── preprocess_csic_v3.py   → features_v3.parquet   (22 features)
└── preprocess_csic_v4.py   → features_v4.parquet   (23 features) ← versión final

notebooks/experiments/
├── csic2010_feature_analysis_v1.ipynb  ← análisis FP baseline
├── csic2010_feature_analysis_v2.ipynb  ← url features
├── csic2010_feature_analysis_v3.ipynb  ← content POST + MLflow
├── csic2010_feature_analysis_v4.ipynb  ← url structure GET
├── csic2010_feature_analysis_v5.ipynb  ← threshold calibration
├── csic2010_feature_analysis_v6.ipynb  ← content_param_density
├── csic2010_fp_analysis_v6.py          ← análisis CSV crudo → root cause
└── csic2010_feature_analysis_v7.ipynb  ← Latin-1 hypothesis (no confirmada)
```

**MLflow:** experimento `mlsec-model-a`, backend SQLite `mlflow.db`. 28 runs, naming `model-a-{algoritmo}-features-{version}`.

---

## Modelo B — UNSW-NB15 (en progreso)

### Dataset

UNSW-NB15: 257.673 flujos de red (175.341 train / 82.332 test — splits predefinidos). 9 categorías de ataque: Generic (33%), Exploits (28%), Fuzzers (15%), DoS (4%), Reconnaissance (5%), Analysis, Backdoor, Shellcode, Worms. Desbalance inverso: 68% ataques en train.

### Hallazgos del EDA

- `dload` (bytes descargados): correlación -0.394 con el label — tráfico normal descarga más datos
- `rate`, `ct_dst_sport_ltm`: correlación 0.338 / 0.357
- Outliers extremos: `sbytes` max 12M, `sload` max 5.9B → `RobustScaler`
- Features redundantes descartadas: `dwin` (0.99 con `swin`), `dloss` (0.98 con `dpkts`), `is_sm_ips_ports`
- `proto`: 133 valores únicos → top-10 + "other" encoding
- No hay nulos

### Estrategia de preprocessing

- `RobustScaler` para features numéricas continuas (outliers extremos)
- Top-10+other para `proto`, one-hot directo para `service` y `state`
- Splits predefinidos en los parquets — no se hace train/test split propio

### Qué sigue

1. Implementar `preprocess_unsw.py` con las decisiones del EDA
2. Generar `features.parquet` (train + test)
3. Entrenar baseline (RF, XGBoost, LightGBM) — sin LR, no escala bien a 62 features continuas
4. Analizar FP/FN con el mismo workflow que Modelo A
5. Iterar features hasta F1 ≥ 0.88 / ROC-AUC ≥ 0.95

### Diferencias respecto a Modelo A

| Aspecto | Modelo A (CSIC) | Modelo B (UNSW) |
|---|---|---|
| Features de entrada | Texto (URL, body) → ingeniería manual | Numéricas de red → menos ingeniería manual |
| Métrica objetivo | Recall + Precision | F1 + ROC-AUC |
| Desbalance | Leve 59/41 | Inverso 32/68 (más ataques que normal) |
| Splits | Generados por nosotros (70/15/15) | Predefinidos en el dataset |
| Threshold | Calibrado con min_recall_val sweep | Por definir |

---

## Aprendizajes clave del proyecto

**1. El threshold por defecto (0.5) casi siempre es incorrecto.**
En Modelo A, con 41% de positivos, el threshold óptimo fue 0.2573. Fijar el threshold en validation buscando un target de recall mínimo es mucho más robusto que buscar el punto de máxima F1.

**2. Analizar FP en el CSV crudo vale más que agregar features a ciegas.**
El root cause de los FP (confusión Latin-1 vs encoding de ataque) solo fue visible al leer los requests reales. El análisis de correlaciones y feature importance solo dice "la feature X tiene señal" — no dice por qué el modelo falla en casos específicos.

**3. Las correlaciones en la subpoblación relevante, no en el dataset completo.**
`content_param_density` tiene correlación global +0.066 (ruido) pero correlación POST -0.216 (señal real). Calcular correlaciones en el dataset completo para features de body diluyó la señal con los GETs que tienen body vacío.

**4. Los datasets sintéticos tienen quirks que rompen hipótesis razonables.**
CSIC 2010 fue generado con un script que incluye nombres de campo en español en los ataques. Esto hizo que la hipótesis Latin-1 — correcta en teoría — fallara empíricamente. Los datasets de benchmark tienen limitaciones que solo se descubren al inspeccionar los datos crudos.

**5. Identificar el techo práctico es un resultado, no un fracaso.**
Saber que Precision ~0.793 es el límite del enfoque de features HTTP individuales es información valiosa — evita gastar iteraciones en features que no van a mover el needle.
