# Experimentos

Convenciones del proceso de experimentación. Los experimentos de cada modelo están documentados en sus propias secciones:

- [Modelo A — Web Attack Detection](model_a/index.md)
- [Modelo B — Network Attack Detection](model_b/index.md)

---

## Diferencia entre EDA, Preprocessing y Experimento

| Etapa | Pregunta que responde | Punto de partida | Vive en |
|---|---|---|---|
| **EDA** | ¿Qué hay en los datos? ¿Qué features construir? | Sin modelo | `notebooks/eda/` |
| **Preprocessing** | ¿Cómo transformo los datos crudos en features? | Decisiones del EDA | `src/mlsec/data/` |
| **Experimento** | ¿Por qué falla el modelo? ¿Cómo mejorarlo? | Modelo entrenado con resultados conocidos | `notebooks/experiments/` |

El EDA explora los datos sin un modelo previo. El experimento itera sobre un modelo ya entrenado con resultados insatisfactorios — la pregunta no es "¿qué hay en los datos?" sino "¿por qué el modelo falla y cómo lo mejoramos?".

---

## Esquema de versiones

Cada iteración genera una versión numerada del notebook de análisis. El notebook anterior se conserva con sus outputs — no se sobreescribe. Esto permite comparar exactamente qué cambió entre versiones y por qué.

### Relación entre notebooks, preprocessing y parquets

Los números de versión de notebooks y scripts de preprocessing **no son 1:1**. Son ciclos independientes:

- El **notebook** sube de versión en cada iteración de experimentación, aunque no haya features nuevas
- El **script de preprocessing** sube de versión solo cuando se decide incorporar features nuevas al pipeline oficial
- Los notebooks pueden construir features **en memoria** para probarlas antes de agregarlas al preprocessing

Flujo típico:

```
notebook vN          →  prueba features candidatas en memoria
    │
    ├── features sin señal → se descartan, no hay nuevo preprocessing
    │
    └── features con señal → se consolidan en preprocess_csic_v(N+1).py
                                  → genera features_v(N+1).parquet
                                  → próximo notebook parte de ese parquet
```

Ejemplo concreto — de v2 a v3:

```
v2 notebook  →  validó url_pct_density y url_param_count con features_v2.parquet
                    ↓
             preprocess_csic_v2.py genera features_v2.parquet (17 features)
                    ↓
v3 notebook  →  construye content_pct_density en memoria sobre features_v2.parquet
                    ↓ (señal insuficiente sola, pero se incorpora igual por mejora consistente)
             preprocess_csic_v3.py (pendiente) generará features_v3.parquet (19 features)
                    ↓
v4 notebook  →  construirá url_path_depth, url_query_length, url_has_query en memoria
```

Los parquets generados viven en `data/processed/csic2010/`:

```
data/processed/csic2010/
├── features.parquet       ← 15 features — generado por preprocess_csic_v1.py
└── features_v2.parquet    ← 17 features — generado por preprocess_csic_v2.py
```

### Notebooks de experimentos — CSIC 2010

| Versión | Notebook | Parquet de entrada | Estado | Qué hizo |
|---|---|---|---|---|
| v1 | `csic2010_feature_analysis_v1.ipynb` | `features.parquet` | ✅ ejecutado | Feature importance + análisis de FP + 4 features candidatas evaluadas |
| v2 | `csic2010_feature_analysis_v2.ipynb` | `features_v2.parquet` | ✅ ejecutado | 4 modelos re-entrenados con features_v2, comparativa vs v1 |
| v3 | `csic2010_feature_analysis_v3.ipynb` | `features_v2.parquet` + 2 en memoria | ✅ ejecutado | Primera integración MLflow + `content_pct_density` → Precision +0.011 a +0.016, FP -88 |
| v4 | `csic2010_feature_analysis_v4.ipynb` | `features_v2.parquet` + 3 en memoria | ✅ ejecutado | `url_path_depth`, `url_query_length`, `url_has_query` → Precision +0.090, FP -567, ROC-AUC 0.966 |

### Scripts de preprocessing — CSIC 2010

| Versión | Script | Parquet generado | Features | Decidido en |
|---|---|---|---|---|
| v1 | `preprocess_csic_v1.py` | `features.parquet` | 15 + label | EDA original |
| v2 | `preprocess_csic_v2.py` | `features_v2.parquet` | 17 + label | v1 notebook — `url_pct_density`, `url_param_count` |
| v3 | `preprocess_csic_v3.py` | `features_v3.parquet` | 22 + label | v3+v4 notebooks — `content_pct_density`, `content_param_count`, `url_path_depth`, `url_query_length`, `url_has_query` |

---

## Preprocessing oficial vs Preprocessing exploratorio

El término "Preprocessing" en este proyecto tiene dos formas que **no son intercambiables**:

| | Preprocessing oficial | Preprocessing exploratorio |
|---|---|---|
| Dónde vive | `src/mlsec/data/preprocess_csic_vN.py` | Dentro del notebook de experimento |
| Output | Parquet estable en `data/processed/` | Nada — las features existen solo en memoria |
| Cuándo se crea | Después de validar las features | Para probar features candidatas antes de comprometerse |
| Es reproducible | Sí — cualquiera ejecuta el script y obtiene el mismo resultado | Solo en el contexto del notebook |
| Puede descartarse | No — si se creó, hubo una decisión de incorporar | Sí — si no hay señal, no hay nuevo script |

### Flujo del Preprocessing exploratorio — 7 pasos

Un experimento de feature engineering sigue siempre el mismo flujo:

1. **Cargar el parquet más reciente** — la base de features estables ya validadas
2. **Analizar los errores del modelo anterior** — ¿qué tienen en común los FP? ¿Hay un patrón estructural?
3. **Identificar la subpoblación relevante** — si la señal esperada es de body POST, analizar solo POSTs; si es de URL GET, analizar solo GETs
4. **Calcular correlaciones en la subpoblación** — verificar que la feature candidata tiene correlación significativa con el label *en esa subpoblación*
5. **Construir la feature en memoria** — `df["nueva_feature"] = ...` — no se escribe nada a disco
6. **Entrenar el modelo con la feature nueva y medir métricas** — comparar Recall, Precision, FP y ROC-AUC contra el resultado anterior
7. **Concluir: ¿hay señal?** — si las métricas mejoran de forma consistente → incorporar al preprocessing oficial (nuevo script → nuevo parquet); si no hay mejora → descartar, no hay nuevo script

### Qué significa "señal suficiente" en el paso 7

No hay un umbral fijo, pero se buscan estas condiciones:

- **Precision mejora** — el FP count baja con el threshold mantenido
- **Recall se mantiene** — el criterio ≥ 0.95 no se rompe
- **ROC-AUC sube** — la capacidad de separación total mejora
- **Consistencia entre algoritmos** — si solo un modelo mejora y los otros no, la señal puede ser ruido de overfitting

Si la mejora es marginal pero consistente (ej: v3 `content_pct_density` → Precision +0.009 a +0.016 en todos los modelos), se incorpora igual. Si no hay mejora en ningún modelo, la feature se descarta sin dejar rastro en el código.

El resultado del paso 7 determina si el notebook genera un nuevo `preprocess_csic_vN.py` o si el trabajo termina sin cambios al pipeline oficial.

---

## Comparación de métricas vs versión anterior

En cada notebook de experimento, los resultados de la versión anterior se guardan en un diccionario Python al inicio del notebook:

```python
# Resultados de referencia — versión anterior (para calcular deltas)
V3_RESULTS = {
    "LightGBM": {"roc_auc": 0.955, "recall": 0.952, "precision": 0.713, "fp": 1444},
    "RF":       {"roc_auc": 0.950, "recall": 0.950, "precision": 0.704, "fp": 1504},
    ...
}
```

Después de entrenar, se calculan deltas explícitos:

```python
delta_precision = current_precision - V3_RESULTS["LightGBM"]["precision"]
# 0.803 - 0.713 = +0.090
delta_fp = current_fp - V3_RESULTS["LightGBM"]["fp"]
# 877 - 1444 = -567
```

Los resultados se presentan en una tabla con columna Δ para ver de un vistazo qué mejoró y cuánto. La "versión anterior" siempre es la última versión entrenada, no el baseline original — así el delta mide el impacto incremental de las features nuevas.

**Por qué no se compara siempre contra el baseline original:** el baseline tiene 15 features; en v4 se tienen 22. Comparar v4 contra el baseline mezclaría el impacto de las features intermedias (v2, v3) con el impacto de las features de v4. El delta incremental aísla el efecto de cada iteración.

---

## Modelo A — Web Attack Detection (CSIC 2010)

### Training baseline — 4 modelos

**Fecha:** 2026-04-10 / 2026-04-11  
**Script:** `src/mlsec/models/train_model_a.py`  
**Preprocessing:** `preprocess_csic_v1.py` → `features.parquet` (15 features)

#### Hipótesis

Con las 15 features construidas en el EDA (indicadores de texto en URL y content, one-hot de Method, url_length, content_length), un modelo de clasificación debería poder cumplir Recall ≥ 0.95 y Precision ≥ 0.85.

#### Modelos evaluados y resultados

| Modelo | ROC-AUC | Recall | Precision | FP | FN | Estado |
|---|---|---|---|---|---|---|
| Logistic Regression | 0.761 | 1.000 | 0.411 | 5400 | 0 | ❌ predice todo como ataque |
| Random Forest | 0.939 | 0.951 | 0.655 | 1886 | 185 | ❌ Recall ✅ / Precision ❌ |
| XGBoost | 0.933 | 0.964 | 0.594 | 2476 | 137 | ❌ Recall ✅ / Precision ❌ |
| LightGBM | 0.941 | 0.953 | 0.654 | 1894 | 178 | ❌ Recall ✅ / Precision ❌ |

#### Qué encontramos

- **Logistic Regression** predice todo como ataque. Con ROC-AUC 0.76 no tiene capacidad para separar clases — el threshold óptimo para Recall ≥ 0.95 es tan bajo que clasifica todo como positivo. Descartada.
- **RF, XGBoost y LightGBM** cumplen Recall pero no Precision. Los tres se estancan en ~0.94 ROC-AUC — el mismo techo independientemente del algoritmo.
- **El techo uniforme es el diagnóstico clave:** cuando modelos tan distintos (lineal, ensemble paralelo, boosting secuencial) llegan al mismo resultado, el problema no está en el algoritmo sino en la información disponible. Las features no tienen suficiente señal para separar los falsos positivos.
- **Threshold óptimo:** 0.15 para RF — muy por debajo del default 0.5, lo que confirma que asumir 0.5 habría dado Recall insuficiente.

#### Decisión

No tiene sentido probar más algoritmos — el problema está en las features. El próximo paso es entender qué tienen en común los falsos positivos y buscar nueva señal.

---

### Experimento v1 — Análisis de features

**Fecha:** 2026-04-11  
**Notebook:** `notebooks/experiments/csic2010_feature_analysis_v1.ipynb`  
**Preprocessing usado:** `preprocess_csic_v1.py` → `features.parquet` (15 features)

#### Por qué lo hicimos

El training baseline mostró ~1.886 falsos positivos en todos los modelos. El modelo cumple Recall pero clasifica demasiado tráfico normal como ataque. Para mejorar la Precision necesitamos entender qué tienen en común esos FP — qué los hace "sospechosos" para el modelo aunque sean requests legítimos.

#### Opciones consideradas

| Opción | Por qué no la elegimos |
|---|---|
| Probar más algoritmos | El techo ~0.94 ROC-AUC es igual en todos — el problema no es el algoritmo |
| Pasar al Modelo B | Válido para MVP pero deja una deuda técnica sin entender |
| Agregar MLflow primero | Útil para organizar, pero no resuelve el problema de fondo |
| **Feature importance + análisis FP** ← elegida | Aborda la causa raíz: falta de señal en las features |

#### Qué hizo el notebook

1. Re-entrenó el RF base con las 15 features como punto de referencia
2. Calculó feature importance — ranking de contribución de cada feature
3. Comparó los FP contra el tráfico normal bien clasificado (TN) para encontrar el patrón
4. Probó 4 features nuevas candidatas y midió su correlación con el label
5. Entrenó un RF extendido con las features nuevas y comparó métricas

#### Qué encontramos

**Análisis de falsos positivos — el hallazgo central:**

| Feature | FP (confundido) | TN (correcto) | Interpretación |
|---|---|---|---|
| `url_length` | **+0.233** | -0.384 | FP tienen URLs más largas que TN |
| `content_length` | **+0.243** | -0.357 | FP tienen bodies más largos que TN |
| `method_is_post` | 0.302 | 0.177 | FP son más frecuentemente POSTs |
| todos los `url_has_*` | ~0.000 | ~0.000 | **Sin indicadores de payload** |
| todos los `content_has_*` | ~0.000 | ~0.000 | **Sin indicadores de payload** |

Los 1.886 FP **no tienen ningún indicador de ataque**. El modelo los clasifica como ataque únicamente porque tienen URLs o bodies más largos. Aprendió "URL larga = sospechoso", pero hay tráfico normal legítimo con URLs largas que no contiene ningún payload malicioso.

Esto explica directamente por qué la Precision no mejora: el modelo no puede distinguir entre una URL larga con payload de ataque y una URL larga sin payload — ambas se ven igual con las features actuales.

**Correlación de features nuevas candidatas con el label:**

| Feature | Correlación | Decisión |
|---|---|---|
| `url_pct_density` | **0.267** | ✅ señal útil — da contexto a la longitud |
| `url_param_count` | **0.146** | ✅ señal útil — da contexto a la longitud |
| `url_has_traversal` | NaN | ❌ `../` nunca aparece literal — siempre encoded como `%2F` |
| `post_has_pct27` | NaN | ❌ intersección insuficiente en el dataset |

`url_pct_density` da exactamente el contexto que faltaba: una URL larga con alta densidad de chars encoded (`%27`, `%3C`) es muy diferente a una URL larga con texto normal. `url_param_count` complementa esto con el número de parámetros.

`url_has_traversal` y `post_has_pct27` dan NaN por el mismo motivo que los chars literales en el EDA original — los atacantes siempre usan percent-encoding.

**Impacto medido (RF base vs RF extendido con 2 features nuevas):**

| Modelo | ROC-AUC | Recall | Precision |
|---|---|---|---|
| RF base (15 features) | 0.939 | 0.951 ✅ | 0.655 ❌ |
| RF extendido (17 features) | **0.950** | 0.951 ✅ | **0.704** ❌ |

Mejora: +0.011 ROC-AUC y **+0.049 Precision** — confirmado que las features nuevas aportan señal real.

#### Decisión tomada

Agregar `url_pct_density` y `url_param_count` al preprocessing oficial. Crear `preprocess_csic_v2.py` con estas dos features y re-entrenar los 4 modelos para confirmar la mejora con el pipeline completo.

---

### Experimento v2 — Re-entrenamiento con features nuevas

**Fecha:** 2026-04-11  
**Notebook:** `notebooks/experiments/csic2010_feature_analysis_v2.ipynb`  
**Preprocessing usado:** `preprocess_csic_v2.py` → `features_v2.parquet` (17 features)

#### Qué cambió respecto a v1

Se incorporaron las dos features validadas en v1 al preprocessing oficial:

| Feature nueva | Qué mide | Por qué ayuda |
|---|---|---|
| `url_pct_density` | Ratio de chars encoded (`%XX`) sobre longitud total de URL | Da contexto a url_length — una URL larga con alta densidad de encoding es muy diferente a una URL larga con texto normal |
| `url_param_count` | Cantidad de parámetros en la URL (conteo de `=`) | Los ataques suelen tener más parámetros para inyectar payloads |

Se descartaron `url_has_traversal` y `post_has_pct27` porque dieron NaN en v1 — sin señal.

Este notebook re-entrena los **4 modelos completos** (no solo RF) con `features_v2.parquet` para confirmar la mejora en todos los algoritmos y con el pipeline oficial de preprocessing.

#### Resultados

| Modelo | ROC-AUC v2 | Δ vs v1 | Recall v2 | Δ vs v1 | Precision v2 | Δ vs v1 | FP v2 | Δ FP |
|---|---|---|---|---|---|---|---|---|
| Logistic Regression | 0.767 | +0.006 | 0.958 ✅ | -0.042 | 0.420 ❌ | +0.009 | 4971 | -429 |
| Random Forest | 0.950 | +0.011 | 0.950 ✅ | -0.001 | **0.704** ❌ | **+0.049** | 1504 | -382 |
| XGBoost | 0.945 | +0.012 | 0.963 ✅ | -0.001 | 0.633 ❌ | +0.039 | 2100 | -376 |
| LightGBM | **0.953** | **+0.012** | 0.953 ✅ | +0.000 | **0.702** ❌ | **+0.048** | 1523 | -371 |

#### Qué encontramos

- **Mejora consistente en todos los modelos** — el incremento no es casualidad estadística: todos suben ROC-AUC entre +0.006 y +0.012, y Precision entre +0.009 y +0.049. Dos features nuevas generaron mejora real y medible.
- **Reducción de FP:** RF reduce de 1.886 a 1.504 (-382), LightGBM de 1.894 a 1.523 (-371). Hay ~380 requests normales que el modelo ya no clasifica incorrectamente como ataque.
- **El techo sube:** de ~0.94 a ~0.95 ROC-AUC — no llegamos al límite de información, hay más señal disponible.
- **Brecha restante:** Precision máxima es 0.704 (RF y LightGBM) vs criterio de 0.85 — quedan 0.146 por cerrar.
- **Nota técnica:** LightGBM genera un warning menor (`X does not have valid feature names`) porque recibe numpy arrays en lugar de DataFrame. No afecta los resultados.

#### Decisión tomada

Continuar iterando. La mejora de +0.049 Precision con solo 2 features nuevas confirma que hay más señal disponible en el dataset. La siguiente iteración debe enfocarse en el **content POST** — los ataques POST tienen body 35% más largo (hallazgo del EDA) pero los indicadores de content actuales tienen correlación baja con el label. Hay señal sin explotar ahí.

Antes de crear v3, integrar **MLflow** para trackear los experimentos de forma sistemática.

---

### Experimento v3 — Análisis content POST + MLflow

**Fecha:** 2026-04-11  
**Notebook:** `notebooks/experiments/csic2010_feature_analysis_v3.ipynb`  
**Preprocessing base:** `preprocess_csic_v2.py` → `features_v2.parquet` (17 features) + 2 features nuevas construidas en memoria

#### Por qué lo hicemos

v2 llegó a Precision 0.704 — brecha restante de 0.146 para alcanzar 0.85. Las dos features que agregamos en v2 (`url_pct_density`, `url_param_count`) dan contexto a la **longitud de URL**. La hipótesis para v3 es que aplica el mismo razonamiento al **body de los requests POST**: `content_length` solo no distingue entre un body largo con payload de ataque y un body largo con contenido legítimo.

El EDA original mostró que los ataques POST tienen body 35% más largo que el tráfico normal POST, pero los `content_has_*` actuales tienen baja correlación con el label porque se calculan sobre todo el dataset (incluyendo GETs, cuyo content siempre es vacío).

#### Qué hace el notebook

1. Analiza los features de content **exclusivamente en la subpoblación POST** — donde content tiene significado real
2. Identifica cuántos de los FP actuales son POSTs vs GETs
3. Evalúa dos features candidatas: `content_pct_density` y `content_param_count`
4. Re-entrena los 4 modelos con 19 features (v2 + 2 nuevas)
5. **Primera integración de MLflow** — cada run se loggea con parámetros, métricas y artefactos en el experimento `mlsec-model-a`

#### Features candidatas evaluadas

| Feature | Qué mide | Hipótesis |
|---|---|---|
| `content_pct_density` | Ratio de chars encoded (`%XX`) sobre longitud total del body | Análogo a `url_pct_density` — distingue body largo con encoding de ataque vs body largo con texto normal |
| `content_param_count` | Cantidad de `=` en el body | Análogo a `url_param_count` — los ataques POST suelen tener más parámetros inyectados |

#### Resultados

| Modelo | ROC-AUC | Δv2 | Recall | Δv2 | Precision | Δv2 | FP | Criterios |
|---|---|---|---|---|---|---|---|---|
| LR | 0.777 | +0.010 | 0.977 | +0.019 | 0.417 | -0.003 | 5138 | ❌ |
| RF | 0.950 | +0.000 | 0.947 | -0.003 | 0.716 | +0.012 | 1416 | ❌ Recall < 0.95 |
| XGBoost | 0.948 | +0.003 | 0.958 | -0.005 | 0.649 | +0.016 | 1946 | ❌ |
| LightGBM | 0.955 | +0.002 | 0.952 | -0.001 | 0.713 | +0.011 | 1444 | ❌ |

**Conclusión:** mejoras consistentes pero insuficientes. `content_pct_density` solo eliminó 88 FP POST de los 569 esperados — los FP POST tampoco tienen encoding en el body, solo son más largos. El 62.2% de FP son GETs y no son atacables con features de content.

**Próxima dirección:** análisis de estructura de URL sobre la subpoblación GET — `url_path_depth`, `url_query_length`, `url_has_query`. Ver `csic2010_feature_analysis_v4.ipynb`.

---

## Modelo B — Network Attack Detection (UNSW-NB15)

_Sin experimentos todavía. Pendiente Phase 3.1 — arrancar después de completar iteraciones de Modelo A o en paralelo._
