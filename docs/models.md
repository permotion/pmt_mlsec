# Modelos

## Decisiones de diseño

### Labels unificados
- `0` = benign / normal
- `1` = malicious / attack

### Threshold de decisión
El threshold **no se asume 0.5**. Se determina por curva ROC/PR
optimizando el criterio de éxito de cada modelo.

### Estrategia de validación
- Split estratificado (preserva distribución de clases)
- `train/val/test`: 70% / 15% / 15%
- Reproducibilidad: `random_state=42` en todos los splits

---

## Modelo A — Web Attack Detection

**Dataset:** CSIC 2010  
**Input:** Features extraídas de requests HTTP  
**Output:** `0` (normal) / `1` (attack)

### Criterios de éxito

| Métrica | Umbral mínimo |
|---|---|
| Recall | ≥ 0.95 |
| Precision | ≥ 0.85 |

### Datos del dataset (post-EDA)

| Campo | Valor |
|---|---|
| Total registros | 61.065 |
| Columnas originales | 17 |
| Normal (0) | 36.000 (59%) |
| Attack (1) | 25.065 (41%) |
| Requests GET | ~43.088 (70.6%) |
| Requests POST | ~18.977 (29.4%) |

### Estrategia para desbalance de clases

Desbalance leve (59/41) — no requiere SMOTE.
Usar `class_weight='balanced'` en el modelo.

### Dónde viven los ataques

- **GET** → el ataque está en la `URL` (query string)
- **POST** → el ataque está en `content` (body del request)

### Columnas descartadas (post-EDA)

| Columna | Razón |
|---|---|
| `Unnamed: 0` | Redundante con label |
| `host` | 2 valores, sin señal útil |
| `connection` | 2 valores, sin señal útil |
| `language` | Constante — 1 único valor |
| `User-Agent` | Constante — 1 único valor |
| `Pragma` | Constante — 1 único valor |
| `Cache-Control` | Constante — 1 único valor |
| `Accept` | Constante — 1 único valor |
| `Accept-encoding` | Constante — 1 único valor |
| `Accept-charset` | Constante — 1 único valor |
| `content-type` | Constante entre no-nulos — 1 único valor |

### Nulos — estrategia

| Columna | Nulos | Estrategia |
|---|---|---|
| `content`, `lenght`, `content-type` | 70.56% | No imputar — son NaN por diseño en GETs |
| `Accept` | 0.65% | Imputar con moda o descartar |

### Features candidatas (post-EDA inicial)

| Feature | Fuente | Tipo | Notas |
|---|---|---|---|
| `method_is_put` | `Method` | Binaria | **100% ataques** — feature más poderosa |
| `method_is_post` | `Method` | Binaria | 54% tasa de ataque |
| `url_length` | `URL` | Numérica | URLs de ataque suelen ser más largas |
| `content_length` | `content` | Numérica | 0 en GETs, presente en POSTs |
| `url_has_sq` | `URL` | Binaria | Presencia de `'` — SQLi |
| `url_has_lt/gt` | `URL` | Binaria | Presencia de `<>` — XSS |
| `url_has_dashdash` | `URL` | Binaria | Presencia de `--` — SQLi |
| `url_has_select` | `URL` | Binaria | Keyword SQL |
| `url_has_union` | `URL` | Binaria | Keyword SQL |
| `url_has_script` | `URL` | Binaria | Keyword XSS |
| `url_has_pct27` | `URL` | Binaria | `'` URL-encoded |
| `content_has_*` | `content` | Binaria | Mismos indicadores en body POST |

> Correlaciones exactas con el label: pendiente sección 7-8 del notebook.

### Modelos a evaluar (en orden)

1. **Baseline:** Logistic Regression
2. Random Forest
3. Gradient Boosting (XGBoost / LightGBM)

### Resultados de training — Phase 3.1

Split estratificado 70/15/15 — `random_state=42`.  
Script: `src/mlsec/models/train_model_a.py`

#### Logistic Regression (baseline)

| Split | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| Validation | 1.000 | 0.411 | 0.582 | 0.739 |
| **Test** | **1.000** | **0.411** | **0.582** | **0.761** |

| Criterio | Resultado | Estado |
|---|---|---|
| Recall ≥ 0.95 | 1.000 | ✅ |
| Precision ≥ 0.85 | 0.411 | ❌ |

**Diagnóstico:** el modelo predice todo como ataque. Con ROC-AUC 0.76 no tiene capacidad suficiente para separar clases — el threshold óptimo para Recall ≥ 0.95 colapsa a un valor tan bajo que clasifica todos los registros como ataque. Precision = proporción de ataques en el dataset (41%).

#### Random Forest (200 estimadores)

| Split | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| Validation | 0.950 | 0.649 | 0.771 | 0.936 |
| **Test** | **0.951** | **0.655** | **0.775** | **0.939** |

Confusion matrix (test):

```
TN=3514  FP=1886
FN=185   TP=3575
```

| Criterio | Resultado | Estado |
|---|---|---|
| Recall ≥ 0.95 | 0.951 | ✅ |
| Precision ≥ 0.85 | 0.655 | ❌ |

**Diagnóstico:** Recall cumplido. Precision insuficiente — 1.886 falsos positivos. Mejor modelo hasta ahora pero el techo de ROC-AUC (~0.94) sugiere que el problema está en las features, no en el algoritmo.

#### XGBoost (200 estimadores)

| Split | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| Validation | 0.957 | 0.586 | 0.727 | 0.927 |
| **Test** | **0.964** | **0.594** | **0.735** | **0.933** |

Confusion matrix (test):

```
TN=2924  FP=2476
FN=137   TP=3623
```

| Criterio | Resultado | Estado |
|---|---|---|
| Recall ≥ 0.95 | 0.964 | ✅ |
| Precision ≥ 0.85 | 0.594 | ❌ |

**Diagnóstico:** Recall más alto (0.964) pero Precision más baja (0.594) — más FP que Random Forest. El threshold más agresivo (0.117) genera más falsas alarmas.

#### LightGBM (200 estimadores)

| Split | Recall | Precision | F1 | ROC-AUC |
|---|---|---|---|---|
| Validation | 0.953 | 0.648 | 0.772 | 0.938 |
| **Test** | **0.953** | **0.654** | **0.776** | **0.941** |

Confusion matrix (test):

```
TN=3506  FP=1894
FN=178   TP=3582
```

| Criterio | Resultado | Estado |
|---|---|---|
| Recall ≥ 0.95 | 0.953 | ✅ |
| Precision ≥ 0.85 | 0.654 | ❌ |

**Diagnóstico:** Resultados casi idénticos a Random Forest. Mejor ROC-AUC (0.941) pero misma Precision. Confirma que el techo del modelo está en las features actuales.

#### Resumen comparativo — Phase 3.1

| Modelo | ROC-AUC | Recall | Precision | FP | FN | Estado |
|---|---|---|---|---|---|---|
| Logistic Regression | 0.761 | 1.000 | 0.411 | 5400 | 0 | ❌ predice todo como ataque |
| Random Forest | 0.939 | 0.951 | 0.655 | 1886 | 185 | ❌ Precision insuficiente |
| XGBoost | 0.933 | 0.964 | 0.594 | 2476 | 137 | ❌ Precision insuficiente |
| LightGBM | **0.941** | 0.953 | 0.654 | 1894 | 178 | ❌ Precision insuficiente |

!!! warning "Techo de features"
    Todos los modelos llegan a ~0.94 ROC-AUC con las 15 features actuales. El cuello de botella no es el algoritmo — es la cantidad de información disponible. Las features de `content` (body POST) están incompletas: `content_has_*` se calcula pero no se están aprovechando bien para diferenciar ataques POST de tráfico normal.

!!! info "Threshold óptimo"
    El threshold se optimizó en val buscando Recall ≥ 0.95 con la mayor Precision posible. Los valores resultantes (0.15–0.17) son mucho más bajos que el default 0.5 — confirma que asumir 0.5 habría dado Recall insuficiente.

#### Próximo paso — mejora de features

Para superar el techo de Precision, las opciones son:

1. **Agregar features de content** — los indicadores `content_has_*` existen pero falta analizar su poder discriminativo en ataques POST específicamente
2. **Feature importance** — identificar qué features aportan más y si hay señal sin explotar
3. **Combinar method + indicadores** — features cruzadas como `is_post_AND_has_pct27`

---

## Modelo B — Network Attack Detection

**Dataset:** UNSW-NB15  
**Input:** 49 features de flujo de red  
**Output:** `0` (benign) / `1` (malicious)

### Criterios de éxito

| Métrica | Umbral mínimo |
|---|---|
| F1 | ≥ 0.88 |
| ROC-AUC | ≥ 0.95 |

### Features principales

Del paper original UNSW-NB15:
`dur`, `proto`, `service`, `state`, `spkts`, `dpkts`, `sbytes`, `dbytes`,
`rate`, `sttl`, `dttl`, `sload`, `dload`, `ct_srv_src`

### Modelos a evaluar (en orden)

1. **Baseline:** Random Forest (buen desempeño conocido en este dataset)
2. XGBoost
3. LightGBM

### Datos del dataset (post-EDA)

| Campo | Valor |
|---|---|
| Train shape | 175.341 × 36 |
| Test shape | 82.332 × 36 |
| Benign train (0) | 56.000 (31.9%) |
| Malicious train (1) | 119.341 (68.1%) |
| Benign test (0) | 37.000 (44.9%) |
| Malicious test (1) | 45.332 (55.1%) |
| Split | Predefinido en parquet — no modificar |

### Columnas descartadas (post-EDA)

| Columna | Razón |
|---|---|
| `dwin` | 0.99 correlación con `swin` — redundante |
| `dloss` | 0.98 correlación con `dpkts` — redundante |
| `is_sm_ips_ports` | 0.94 correlación con `sinpkt`, menor correlación con label |
| `attack_cat` | Solo para análisis — label categórico de los 9 tipos de ataque |

### Estrategia de preprocessing (post-EDA)

| Aspecto | Decisión |
|---|---|
| **Nulos** | Sin imputación — dataset completo, sin nulos |
| **Normalización** | `RobustScaler` — outliers extremos en sbytes, sload, dload |
| **proto** (133 valores) | Top-10 + categoría `other` → one-hot |
| **service** (13 valores) | One-hot directo |
| **state** (9 valores) | One-hot directo |
| **`-` en service** | No es nulo — es categoría "sin servicio", se mantiene |

### Nota sobre desbalance de clases

UNSW-NB15 tiene **más ataques que tráfico normal** (68% malicious en train). Estrategia inicial: `class_weight='balanced'`. Si no alcanza, evaluar SMOTE en training set únicamente. Ajuste de threshold post-entrenamiento siempre.

---

## Registro de decisiones

| Fecha | Decisión | Razón |
|---|---|---|
| 2026-04-06 | Labels: 0=benign, 1=attack | Consistencia entre modelos |
| 2026-04-06 | Detección offline en MVP | Simplifica arquitectura inicial |
| 2026-04-06 | Threshold no fijo en 0.5 | Optimizar Recall en ataques |
| 2026-04-06 | Airflow en Phase 4 | Evitar complejidad prematura |
| 2026-04-06 | No usar SMOTE en Modelo A | Desbalance leve 59/41 — class_weight='balanced' suficiente |
| 2026-04-06 | Nulos en content/lenght no se imputan | Son NaN por diseño HTTP en requests GET |
| 2026-04-06 | Features basadas en URL y content | Los ataques viven en query string (GET) y body (POST) |
| 2026-04-06 | method_is_put es feature crítica | 100% de requests PUT son ataques en CSIC 2010 |
| 2026-04-06 | Usar caracteres URL-encoded, no literales | `'` crudo nunca aparece — usar `%27`; `<` crudo nunca aparece — usar `%3C` |
| 2026-04-06 | Descartar url_has_union y chars crudos | Correlación ~0 o NaN — sin poder discriminativo en URLs |
| 2026-04-06 | 11 columnas descartadas por ser constantes | nunique()=1, sin información para el modelo |
| 2026-04-06 | UNSW-NB15: split predefinido en parquet se respeta | Dataset tiene train/test oficiales — no re-splitear |
| 2026-04-06 | UNSW-NB15: RobustScaler para features numéricas | Outliers extremos en sbytes (max 12M), sload (max 5.9B) |
| 2026-04-06 | UNSW-NB15: proto top-10+other | 133 valores únicos — one-hot directo generaría demasiadas columnas |
| 2026-04-06 | UNSW-NB15: descartar dwin, dloss, is_sm_ips_ports | Correlación >0.9 con otras features — redundantes |
| 2026-04-06 | UNSW-NB15: mantener stcpb/dtcpb en modelo inicial | Correlación -0.255 inesperada — validar con feature importance post-training |
| 2026-04-06 | UNSW-NB15: estrategia desbalance — class_weight='balanced' primero | Desbalance 68/32 — probar balanced antes de SMOTE |
| 2026-04-10 | Modelo A: LR descartada como baseline | ROC-AUC 0.76 — predice todo como ataque, Precision 0.41 |
| 2026-04-10 | Modelo A: Random Forest cumple Recall (0.951) pero no Precision (0.655) | Threshold óptimo 0.15, 1886 FP — probar XGBoost/LightGBM |
| 2026-04-10 | Modelo A: threshold óptimo 0.15, no 0.5 | Confirma que asumir 0.5 sería insuficiente para el criterio de Recall |
| 2026-04-11 | Modelo A: XGBoost y LightGBM no superan RF | ROC-AUC ~0.94 en todos — techo de features, no de algoritmo |
| 2026-04-11 | Modelo A: FP causados por longitud, no por payload | url_length y content_length solos generan ruido — necesitan contexto |
| 2026-04-11 | Modelo A: url_pct_density y url_param_count mejoran Precision +0.049 | ROC-AUC 0.939→0.950, Precision 0.655→0.704 — agregadas en preprocess_csic_v2.py |
| 2026-04-11 | Modelo A: url_has_traversal y post_has_pct27 descartadas | NaN — nunca aparecen literales, siempre percent-encoded |
| 2026-04-11 | Modelo A v2: mejor modelo LightGBM ROC-AUC 0.953, Precision 0.702 | Brecha restante 0.148 para llegar a Precision 0.85 — continuar con v3 |
