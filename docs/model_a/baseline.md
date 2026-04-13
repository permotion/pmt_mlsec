# Baseline — 4 modelos

**Fecha:** 2026-04-10 / 2026-04-11  
**Script:** `src/mlsec/models/train_model_a.py`  
**Preprocessing:** `preprocess_csic_v1.py` → `features.parquet` (15 features)

---

## Función de este paso

El baseline training tiene una sola función: **saber si las 15 features del EDA tienen suficiente señal para cumplir los criterios del MVP**.

No es para afinar el modelo — es para responder una pregunta binaria:

> ¿Con esta información, algún algoritmo puede llegar a Recall ≥ 0.95 y Precision ≥ 0.85?

- Si la respuesta es **sí** → el problema está en el algoritmo o los hiperparámetros, hay que explorar ahí
- Si la respuesta es **no** → el problema está en las features, no tiene sentido seguir probando algoritmos

Por eso se entrenan 4 modelos muy distintos entre sí — si todos llegan al mismo techo, la conclusión es inequívoca: el cuello de botella es la información disponible, no el modelo.

---

## Hipótesis

Con las 15 features construidas en el EDA (indicadores de texto en URL y content, one-hot de Method, url_length, content_length), un modelo de clasificación debería poder cumplir Recall ≥ 0.95 y Precision ≥ 0.85.

---

## Features de entrada — `features.parquet` (15 features)

Generadas por `preprocess_csic_v1.py` a partir del CSV crudo `csic_database.csv`. Las columnas originales sin señal (User-Agent, headers HTTP, cookie, etc.) fueron descartadas en el EDA.

**Method** — one-hot encoding de la columna `Method`

| Feature | Qué representa |
|---|---|
| `method_is_get` | El request es GET |
| `method_is_post` | El request es POST |
| `method_is_put` | El request es PUT |

**URL** — extraído de la columna `URL`

| Feature | Qué representa |
|---|---|
| `url_length` | Longitud total de la URL en caracteres |
| `url_has_pct27` | La URL contiene `%27` (`'` percent-encoded — SQLi) |
| `url_has_pct3c` | La URL contiene `%3C` (`<` percent-encoded — XSS) |
| `url_has_dashdash` | La URL contiene `--` (comentario SQL) |
| `url_has_script` | La URL contiene `script` (keyword XSS) |
| `url_has_select` | La URL contiene `SELECT` (keyword SQL) |

**Content** — extraído del body del request (solo relevante en POSTs; GETs tienen `content_length=0`)

| Feature | Qué representa |
|---|---|
| `content_length` | Longitud del body en caracteres |
| `content_has_pct27` | El body contiene `%27` |
| `content_has_pct3c` | El body contiene `%3C` |
| `content_has_dashdash` | El body contiene `--` |
| `content_has_script` | El body contiene `script` |
| `content_has_select` | El body contiene `SELECT` |

!!! note "Por qué percent-encoding y no caracteres literales"
    Los atacantes siempre usan percent-encoding para evadir filtros — `'` nunca aparece literal en las URLs del dataset, siempre como `%27`. Buscar el caracter literal daría correlación NaN. Esto se descubrió en el EDA y es una decisión de diseño central del preprocessing.

---

## Algoritmos evaluados

Se eligieron 4 algoritmos con enfoques fundamentalmente distintos para que el resultado sea concluyente:

| Algoritmo | Enfoque | Parámetros clave |
|---|---|---|
| **Logistic Regression** | Lineal — el más simple, sirve como piso de referencia | `class_weight='balanced'`, `max_iter=1000` |
| **Random Forest** | Ensemble paralelo — 200 árboles independientes que votan | `n_estimators=200`, `class_weight='balanced'` |
| **XGBoost** | Boosting secuencial — cada árbol corrige los errores del anterior | `n_estimators=200`, `scale_pos_weight=neg/pos` |
| **LightGBM** | Boosting con histogramas — más rápido que XGBoost en datasets grandes | `n_estimators=200`, `scale_pos_weight=neg/pos` |

La diversidad es intencional: si un modelo lineal, un ensemble paralelo y dos variantes de boosting llegan al mismo resultado, el problema no está en el algoritmo.

---

## Split 70/15/15 estratificado

El dataset se divide en tres subsets:

| Subset | % | Tamaño aprox. | Uso |
|---|---|---|---|
| **Train** | 70% | ~42.700 requests | El modelo aprende con estos datos — `fit()` |
| **Val** | 15% | ~9.200 requests | Se busca el threshold óptimo — el modelo no entrena aquí |
| **Test** | 15% | ~9.200 requests | Se reportan las métricas finales — no se toca hasta el final |

**Estratificado** significa que cada subset mantiene la misma proporción de clases que el dataset original (59% normal / 41% ataque). Sin estratificación podría quedar un subset con muchos más ataques que otro por azar, haciendo la evaluación no representativa.

**Por qué tres subsets y no dos:** con solo train/test, el threshold se optimizaría sobre el test y las métricas finales quedarían sesgadas — el modelo habría tomado una decisión usando el mismo conjunto con el que se lo evalúa. El val set existe para tomar esa decisión de forma limpia.

Los mismos tres subsets se usan para los 4 modelos — no se regenera el split por modelo.

---

## Configuración del entrenamiento

- **Split:** 70/15/15 estratificado, `random_state=42`
- **Scaling:** StandardScaler en `url_length` y `content_length` (fit solo en train)
- **Threshold:** Optimizado en val → maximiza Precision dado Recall ≥ 0.95 (no se asume 0.5)
- **Balance de clases:** `class_weight='balanced'` (LR, RF) / `scale_pos_weight` (XGBoost, LightGBM)

---

## Escalado de features (StandardScaler)

### Por qué se escalan solo dos features

El dataset tiene dos tipos de features:

| Tipo | Features | Rango de valores | ¿Se escala? |
|---|---|---|---|
| **Continuas** | `url_length`, `content_length` | 0–400 / 0–836 | ✅ Sí |
| **Binarias** | `url_has_*`, `content_has_*`, `method_is_*` | Solo 0 o 1 | ❌ No — ya están en la misma escala |

Comparando valores reales del dataset:

```
   url_length  content_length  url_has_pct27  method_is_post
0          48               0              0               0
1         126               0              0               0
2          57              68              0               1
3         125               0              0               0
4          61              63              0               1
14        292               0              0               0
15         59             232              0               1
```

`url_length` vale 48, 126, 292... `url_has_pct27` solo vale 0 o 1. Sin escalar, un modelo lineal como Logistic Regression le daría más peso a `url_length` simplemente por tener valores más grandes — no porque sea más importante.

StandardScaler transforma las continuas para que tengan **media 0 y desviación estándar 1**:

```
valor_escalado = (valor_original - media_train) / std_train

# Ejemplo con url_length (media_train ≈ 97, std_train ≈ 71):
url_length = 48  → (48  - 97) / 71 = -0.69   (URL corta)
url_length = 97  → (97  - 97) / 71 =  0.00   (URL promedio)
url_length = 292 → (292 - 97) / 71 = +2.75   (URL muy larga)
```

Después del escalado todas las features están en rangos comparables — el modelo puede ponderar su importancia de forma justa.

### Por qué fit solo en train

El `fit` es el momento en que el scaler **mira los datos y aprende** la media y la desviación estándar:

```python
# Aprende media y std mirando SOLO el train
scaler.fit(X_train)
#   url_length:     media=97,  std=71
#   content_length: media=28,  std=59

# Transforma cada subset con esos mismos números
scaler.transform(X_train)   # usa media=97, std=71
scaler.transform(X_val)     # usa LOS MISMOS media=97, std=71
scaler.transform(X_test)    # ídem
```

Si se hiciera `fit` en val o test, el scaler calcularía una media y std distintas para cada subset. Eso es **data leakage**: el pipeline se prepararía con información de datos que en producción nunca vería antes de predecir.

En producción, cuando llega un request nuevo, la única escala disponible es la que se aprendió en train — exactamente lo que se replica acá.

---

## Búsqueda del threshold óptimo

El modelo no predice "ataque" o "normal" directamente — predice una **probabilidad** entre 0 y 1. El threshold es el corte: si la probabilidad es mayor o igual al threshold, el modelo clasifica como ataque.

El threshold por defecto en scikit-learn es 0.5, pero eso asume que ambos errores (FP y FN) tienen el mismo costo. En seguridad no es así — dejar pasar un ataque (FN) es peor que disparar una falsa alarma (FP). La función `find_best_threshold` busca el threshold que cumple el criterio de Recall mínimo con la mayor Precision posible:

```python
def find_best_threshold(y_true, y_proba):
    # Calcula precision, recall y threshold para cada punto de corte posible
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_proba)

    # Filtra solo los thresholds donde Recall >= 0.95
    mask = recalls[:-1] >= MIN_RECALL  # MIN_RECALL = 0.95

    # De los que cumplen Recall, elige el que tiene mayor Precision
    best_idx = np.where(mask, precisions[:-1], 0).argmax()

    return thresholds[best_idx]
```

Visualmente, la curva Precision-Recall muestra el trade-off en todos los thresholds posibles:

```
Precision
  1.0 │
  0.8 │              ╭──────
  0.6 │         ╭───╯      ╲
  0.4 │    ╭───╯            ╲
  0.2 │╭──╯                  ╲
  0.0 └────────────────────────── Recall
      0.0  0.2  0.4  0.6  0.8  1.0
                              ↑
                         threshold óptimo:
                         máxima Precision
                         con Recall ≥ 0.95
```

El resultado: RF necesita threshold **0.15** para cumplir Recall ≥ 0.95. Si se usara 0.5, el Recall caería significativamente porque el modelo sería demasiado conservador para clasificar como ataque.

---

## Cómo se aplica cada subset

El entrenamiento ocurre una sola vez con el train set. Val y test solo reciben predicciones — el modelo no aprende nada de ellos.

```python
# 1. El modelo aprende — SOLO con train
model.fit(X_train, y_train)

# 2. Predice probabilidades en val — no aprende, solo predice
val_proba = model.predict_proba(X_val)[:, 1]
# → [0.82, 0.03, 0.91, 0.14, ...]
#   cada número = probabilidad de que el request sea un ataque

# 3. Busca el threshold óptimo en val
threshold = find_best_threshold(y_val, val_proba)
# → ej: 0.15 (el corte que da Recall >= 0.95 con mejor Precision)

# 4. Convierte probabilidades en predicciones 0/1
val_pred = (val_proba >= threshold).astype(int)

# 5. Aplica el mismo threshold en test
test_proba = model.predict_proba(X_test)[:, 1]
test_pred  = (test_proba >= threshold).astype(int)

# 6. Métricas finales — estas son las que se reportan
recall    = recall_score(y_test, test_pred)
precision = precision_score(y_test, test_pred)
roc_auc   = roc_auc_score(y_test, test_proba)
```

Este flujo se repite de forma idéntica para los 4 modelos, sobre los mismos subsets.

!!! important "Por qué val y test nunca participan en el fit"
    Val y test son datos que el modelo nunca vio durante el `fit()`. Al predecir sobre ellos, el modelo aplica lo que aprendió en train a datos nuevos — simulando lo que pasaría en producción con requests reales. Si el modelo hubiera visto el test durante el entrenamiento, las métricas serían artificialmente altas y no reflejarían el comportamiento real.

    El val set existe específicamente para buscar el threshold sin "contaminar" el test. Si se optimizara el threshold sobre el test, las métricas finales quedarían sesgadas — el modelo habría tomado una decisión (el threshold) usando el mismo conjunto con el que se lo evalúa.

---

## Cómo leer el reporte final

Por cada modelo se reportan 4 métricas que se leen juntas — ninguna sola cuenta la historia completa:

**Confusion matrix — el punto de partida**

La confusion matrix muestra exactamente cuántos requests cayeron en cada categoría. Para Random Forest en el baseline:

```
                  Predicho: Normal   Predicho: Ataque
Real: Normal  →       TN = 3.514         FP = 1.886
Real: Ataque  →       FN =   185         TP = 3.575
```

- **TP (3.575):** ataques detectados correctamente ✅
- **TN (3.514):** tráfico normal clasificado correctamente ✅
- **FP (1.886):** tráfico normal clasificado como ataque ❌ — falsas alarmas
- **FN (185):** ataques que pasaron sin detectar ❌ — el error más costoso en seguridad

**Las 4 métricas derivadas de esa matriz:**

| Métrica | Fórmula | RF Baseline | Criterio | Interpretación |
|---|---|---|---|---|
| **Recall** | TP / (TP + FN) | 0.951 ✅ | ≥ 0.95 | De 3.760 ataques reales, detectó 3.575. 185 pasaron sin alarma |
| **Precision** | TP / (TP + FP) | 0.655 ❌ | ≥ 0.85 | De 5.461 alarmas disparadas, 3.575 eran ataques reales. 1.886 eran falsas alarmas |
| **ROC-AUC** | Área bajo curva ROC | 0.939 | — | Capacidad de separar clases en todos los thresholds. Independiente del threshold elegido |
| **F1** | 2×(P×R)/(P+R) | 0.772 | — | Resumen de Precision y Recall. No es el criterio de decisión en Modelo A |

**Cómo decidir con estas 4 métricas juntas:**

```
¿Recall ≥ 0.95?
    ├── No → Modelo descartado. No importa el resto.
    └── Sí → ¿Precision ≥ 0.85?
                ├── No → Hay trabajo de features. Ver ROC-AUC para entender el techo.
                └── Sí → Candidato a producción. Validar en test set completo.
```

Para RF baseline: Recall ✅ pero Precision ❌ (0.655 vs 0.85). El ROC-AUC 0.939 indica que hay capacidad de separación — el modelo puede mejorar con mejores features.

---

## Resultados

| Modelo | ROC-AUC | Threshold | Recall | Precision | FP | FN | Estado |
|---|---|---|---|---|---|---|---|
| Logistic Regression | 0.761 | ~0.30 | 1.000 | 0.411 | 5400 | 0 | ❌ predice todo ataque |
| Random Forest | 0.939 | 0.15 | 0.951 | 0.655 | 1886 | 185 | ❌ Precision insuficiente |
| XGBoost | 0.933 | — | 0.964 | 0.594 | 2476 | 137 | ❌ Precision insuficiente |
| LightGBM | 0.941 | — | 0.953 | 0.654 | 1894 | 178 | ❌ Precision insuficiente |

---

## Análisis

**Logistic Regression:** ROC-AUC 0.76 — no tiene capacidad para separar clases. El threshold óptimo para Recall ≥ 0.95 cae a ~0.30, clasificando prácticamente todo como ataque. Descartada para iteraciones siguientes.

**Feature ceiling:** RF, XGBoost y LightGBM son algoritmos muy distintos (ensemble paralelo, boosting con gradient descent, boosting con histogramas) y los tres llegan exactamente al mismo techo de ~0.94 ROC-AUC. Cuando modelos tan distintos producen el mismo resultado, el problema no está en el algoritmo — está en la información disponible. Las features no tienen suficiente señal para separar los falsos positivos.

**Threshold óptimo:** RF necesita threshold 0.15 (muy por debajo de 0.5) para alcanzar Recall ≥ 0.95. Esto confirma que asumir threshold=0.5 habría dado Recall insuficiente.

---

## Decisión

No tiene sentido probar más algoritmos. El problema está en las features — el siguiente paso es entender qué tienen en común los falsos positivos y buscar nueva señal.

→ Ver [v1 — Análisis de features](v1.md)
