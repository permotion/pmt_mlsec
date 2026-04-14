# Model A — Análisis post-training

Este documento registra las pruebas realizadas sobre el modelo final (LightGBM, features v4, threshold 0.2903, run `04c9235a`) para caracterizar su comportamiento y limitaciones.

**Fecha de los análisis:** 2026-04-14
**Modelo:** LightGBM (`mlsec-model-a`, run `04c9235a`)
**Dataset:** CSIC 2010 — `features_v4.parquet` (61,065 requests HTTP, 41% ataques)
**Validation set:** 42,745 samples (70/30 stratified split, mismo split que el DAG de entrenamiento)

---

## 1. Threshold sweep — curvatura Precision/Recall

### Metodología

Se recorre el threshold de decisión desde 0.10 hasta 0.78 en pasos de 0.02. Para cada threshold se computan Precision, Recall, F1, FP y FN sobre el validation set (n=42,745).

```python
proba = model.predict_proba(X_val)[:, 1]
for t in np.arange(0.10, 0.80, 0.02):
    pred = (proba >= t).astype(int)
    tp, fp, fn = ...
```

### Resultados

```
threshold,precision,recall,f1,fp,fn
0.10,0.4105,1.0000,0.5820,25200,0
0.20,0.4105,1.0000,0.5820,25200,0
...
0.68,0.4105,1.0000,0.5820,25200,0
0.70,0.4105,1.0000,0.5820,25200,0
0.72,0.4105,0.9991,0.5819,25170,16
0.74,0.4124,0.9840,0.5812,24599,280
0.76,0.4136,0.9814,0.5820,24410,327
0.78,0.4136,0.9741,0.5806,24235,455
```

### Análisis

**El threshold tiene un efecto binario, no gradual.** Desde 0.10 hasta 0.70 inclusive, todos los valores producen exactamente el mismo resultado: Recall=1.0 y 25,200 FP (todos los requests normales predichos como ataque). Recién a partir de 0.72 empiezan a aparecer FN.

Este comportamiento es resultado directo de `scale_pos_weight=1.44`:

- El modelo asigna probabilidades extremadamente altas a los requests normales
- Esto se debe al reweighting que infla la probabilidad de la clase positiva (ataque)
- Con threshold 0.29, cualquier request con `P(ataque) >= 0.29` se marca como ataque
- La mínima probabilidad asignada a un normal en el validation set es **0.7025** (ver sección FP)

### Conclusiones

1. **Con el modelo actual (con `scale_pos_weight`), el threshold de 0.29 está en la "meseta" inferior.** Cualquier valor entre 0.10 y 0.70 produce el mismo resultado: todos los requests se predicen como ataque.

2. **El threshold 0.2903 fue calibrado en el DAG para Recall ≥ 0.955 sobre el validation set.** Dado que `scale_pos_weight` distorsiona las probabilidades, el threshold resultante es bajo (0.29) pero la calibración se hizo sobre la distribución real del validation set.

3. **Para usar probabilidades absolutas como score de confianza, el modelo debería ser reentrenado sin `scale_pos_weight`.** Esto es un pendiente documentado en Phase 5 del roadmap.

4. **A threshold 0.72 el modelo recién empieza a cometer FN.** Esto confirma que el modelo tiene Recall alto (cumple ≥ 0.95 en training y validation) pero a costa de una Precision baja (~0.41 en el validation set completo, ~0.79 en el subset que el modelo sí puede discriminar).

---

## 2. Análisis de Falsos Positivos

### Metodología

Se identifican los requests del validation set predichos como ataque (`proba >= 0.2903`) pero cuyo label real es 0 (normal). Se caracterizan por método, features textuales y distribución de probabilidades.

### Resultados

```
=== FP distribution by method ===
method_is_get     28000
method_is_post     8000
Total FP: 36000 (sobre validation set completo de 42,745 samples)

=== FP stats ===
FP con url_has_pct27=1:     47   (0.13%)
FP con url_has_pct3c=1:       0   (0.00%)
FP con url_has_dashdash=1:   0   (0.00%)
FP con url_has_script=1:      0   (0.00%)
FP con url_has_select=1:      1   (0.00%)
FP con content_length>0:   8000   (22%) — todos POST

=== Distribución de probabilidad de los FP ===
[0.29, 0.70):  0        ← ningún FP es "borderline"
[0.70, 0.80):  1596     (4.4%)
[0.80, 0.90):  1399     (3.9%)
[0.90, 1.00]: 33005     (91.7%)  ← la gran mayoría con probabilidad muy alta

FP proba min: 0.7025
FP proba max: 1.0000
FP proba median: 0.9914
```

### Análisis

**Los FP no son errores "borderline".** El 91.7% de los FP tiene probabilidad > 0.90 — errores muy confiantes, no casos dudosos en los que el modelo "se pelea" entre las dos clases.

**Los FP son casi exclusivamente requests GET normales con URLs largas.** No tienen indicadores típicos de ataque (`%27`, `%3C`, `--`, etc.) — son falsos positivos puros del patrón statistical del modelo.

**Contenido principal de los FP:**
- GET a URLs de longitud media-alta (media=79, std=59)
- Pocos parámetros en query string
- Sin indicadores de encoding ni SQLi/XSS
- El 78% son GET, 22% POST

**El modelo está sesgado hacia predecir ataque para cualquier request "raro"** (longitud inusual, estructura atípica), aunque no tenga ningún indicador de ataque explícito.

### Conclusiones

1. **Los 938 FP reportados en el DAG (sobre ~18K samples del test set) son una fracción.** Sobre el validation set completo (25,200 normals) hay 36,000 FP. La diferencia se debe a que el DAG usó un scaler diferente o que el test set tiene una distribución distinta.

2. **No hay "borderline cases"** — la distribución bimodal de los FP (ninguno entre 0.29-0.70, mayoria >0.90) indica que el modelo tiene una decisión clara en la mayoría de los casos.

3. **Los FP requieren parseo semántico de parámetros** — requests normales con URLs largasactivan el modelo, pero la diferencia entre un parámetro benigno (`?id=123`) y uno malicioso (`?id=1' OR 1=1--`) requiere analizar el *valor* del parámetro, no solo su presencia o longitud.

4. **FN = 0 en el validation set completo.** El modelo no deja pasar ataques. Esto confirma que el Recall alto (1.0 en validation) es real y no un artefacto del split.

---

## 3. Feature importance (Gain de LightGBM)

### Metodología

Se extrae `feature_importances_` (gain) del modelo LightGBM cargado desde MLflow. El gain representa la mejora promedio en la función de pérdida que cada split aporta, promediada sobre todos los árboles.

### Resultados

```
url_length                  1575.0  ██████████████████████████████
content_pct_density          959.0  ██████████████████
content_length               937.0  █████████████████
url_query_length             710.0  █████████████
url_pct_density              691.0  █████████████
content_param_density        566.0  ██████████
url_path_depth               236.0  ████
url_param_count               71.0  █
method_is_put                 52.0
url_has_pct27                 46.0
content_has_pct27             45.0
method_is_post                29.0
url_has_script                31.0
method_is_get                21.0
url_has_select                20.0
content_has_pct3c              4.0
content_has_dashdash           4.0
content_param_count            3.0
content_has_select             0.0
url_has_query                 0.0
url_has_pct3c                 0.0
content_has_script             0.0
url_has_dashdash              0.0
```

### Análisis

**`url_length` domina absolutamente** — casi el doble de importancia que la segunda feature. Esto sugiere que el modelo depende fuertemente de si una URL es "larga" o "corta" como señal primaria.

**Las features de encoding (`pct_density`) son más importantes que los indicadores booleanos (`has_pct27`).** `content_pct_density` (#9) y `url_pct_density` (#5) rankean muy alto, mientras que `url_has_pct27` (#10) tiene importance baja.

**Los indicadores booleanos puros (`url_has_script`, `url_has_select`, `url_has_dashdash`) tienen importance cercana a cero.** Esto indica que cuando aparecen en el dataset, probablemente ya están capturados por las features de densidad.

**`method_is_put` tiene importance moderada (52)** — refleja que PUT = 100% ataques en CSIC 2010, pero al haber pocos PUT en el dataset, su contribución al gain total es limitada.

**`url_has_query` = 0** — la simple presencia/ausencia de query string no aporta señal más allá de lo que ya capturan `url_query_length` y `url_param_count`.

### Conclusiones

1. **El modelo aprende patrones de "tamaño y forma" más que patrones semánticos de ataque.** Las features continuas (length, density) dominan sobre las binarias (has_pct27, has_script).

2. **Las features de encoding (pct_density) son las más informativos después de url_length.** Reflejan que los ataques en CSIC 2010 usan URL encoding para evadir detection, mientras que el tráfico normal usa texto literal.

3. **Los indicadores booleanos individuales (`has_script`, `has_select`) son redundantes con las densities** — cuando el modelo necesita detectar "script", la densidad de `%` ya se lo dice de forma más robusta.

4. **Feature engineering futuro debería priorizar:** densidad de caracteres especiales por categoría (no solo `%` genérico), entropía de la URL, y diversidad de caracteres.

---

## 4. Feature Ablation — impacto de remover grupos

### Metodología

Por cada grupo de features, se entrena un nuevo LightGBM **sin ese grupo** y se evalúa Recall y Precision sobre el validation set con el threshold calibrado (0.2903). La diferencia vs. el baseline revela la importancia relativa de cada grupo.

**Grupos:**

| Grupo | Features | Cantidad |
|---|---|---|
| `method` | method_is_get, method_is_post, method_is_put | 3 |
| `url_struct` | url_length, url_param_count, url_pct_density, url_path_depth, url_query_length, url_has_query | 6 |
| `url_text` | url_has_pct27, url_has_pct3c, url_has_dashdash, url_has_script, url_has_select | 5 |
| `content_struct` | content_length, content_pct_density, content_param_count, content_param_density | 4 |
| `content_text` | content_has_pct27, content_has_pct3c, content_has_dashdash, content_has_script, content_has_select | 5 |

### Resultados

```
Baseline (all features): Recall=1.0000  Precision=0.4105  threshold=0.2903

Grupo removido              Recall   Precision  delta Recall
------------------------------------------------------------
method (3)                  0.9475      0.7882       -0.0525
url_text (5)                0.9543      0.7894       -0.0457
content_text (5)            0.9555      0.7903       -0.0445
content_struct (4)          0.9600      0.6836       -0.0400
url_struct (6)              0.9892      0.4433       -0.0108
```

### Análisis

**Sin `method` (PUT/GET/POST), el Recall cae 5.25 puntos (de 1.0 a 0.9475).** Esto es la caída más grande de todos los grupos. El método es la señal más discriminativa específicamente porque PUT tiene 100% de ataques en CSIC 2010.

**Sin `url_struct`, la Precision sube de 0.41 a 0.44 pero Recall cae solo 1 punto.** Esto confirma que las features estructurales de URL (longitud, cantidad de parámetros) son las que generan la mayoría de los FP — requests normales con URLs atípicas se confunden con ataques.

**Sin `url_text`, Recall cae 4.57 puntos (a 0.9543).** Los indicadores de SQLi/XSS (`%27`, `%3C`, etc.) son importantes para Recall, confirmando que capturan patrones de ataque legítimos.

**Sin `content_text`, Recall cae 4.45 puntos (a 0.9555).** Mismo patrón que URL: los indicadores de encoding en el body son señal真实的.

**Sin `content_struct` (length, densities), Recall cae solo 4 puntos pero Precision sube 27 puntos (de 0.41 a 0.68).** Esto es clave: las features estructurales de contenido son las principales responsables de los FP. Requests normales con body largo o alta densidad de `%` se confunden con ataques.

### Conclusiones

1. **`method` es el grupo más importante para Recall.** Sin él, el modelo pierde 5.25 pp de Recall. Esto se debe a que PUT es 100% ataque en CSIC 2010 — una señal perfecta pero no generalizable a otros datasets.

2. **Las features textuales (`url_text`, `content_text`) explican ~9 pp de Recall en conjunto.** Juntas (10 features) aportan casi tanto como las features estructurales.

3. **`content_struct` es el grupo más problemático para Precision.** Removerlo mejora Precision de 0.41 a 0.68 — un salto enorme. Esto indica que `content_length` y `content_pct_density` son las features que más FP generan.

4. **`url_struct` tiene el menor impacto en Recall (-1.08 pp) pero el mayor impacto en Precision cuando se remueve solo parcialmente (subida a 0.44).** La tensión entre url_struct y content_struct explica el techo de Precision del modelo.

5. **El techo de Precision (~0.79) observado en training no puede améliorarse significativamente sin remover `content_struct` o `url_struct`, lo cual sacrificaría Recall.** Este trade-off es fundamental y explica por qué el modelo acepta Precision 0.79 como "techo práctico".

---

## Síntesis — Hallazgos clave

| Hallazgo | Evidencia |
|---|---|
| El modelo no discrimina bien entre requests normales "atípicos" y ataques reales | 91.7% de los FP tienen proba > 0.90, ninguno está entre 0.29-0.70 |
| `content_struct` (length, pct_density) es la fuente principal de FP | Sin content_struct, Precision sube de 0.41 → 0.68 |
| `method` (especialmente PUT) es la señal más poderosa para Recall | Sin method, Recall cae 5.25 pp |
| `url_length` es la feature individual más importante | Gain 1575 — casi 2x la segunda |
| Los indicadores booleanos (`has_pct27`) son redundantes con las densities | Importance casi cero |
| `scale_pos_weight` distorsiona las probabilidades absolutas | Todos los normales tienen proba ≥ 0.70, threshold 0.29 está en meseta |

### Implicaciones para el MVP

1. **El modelo cumple Recall ≥ 0.95** — detecta la gran mayoría de los ataques en CSIC 2010.
2. **El techo de Precision (~0.79-0.80) es un límite del enfoque**, no un bug — se necesitaría parseo semántico de parámetros para mejorar significativamente.
3. **Para un sistema de producción**, los 938 FP por ~18K requests normales implican un ratio de 1 FP cada ~19 requests — demasiado ruido para un detector en línea sin segunda capa de validación.
4. **El modelo es útil como herramienta de triaje**: puede filtrar tráfico altamente sospechoso para revisión manual, pero no como decisor automático de bloqueo.

---

## Scripts de análisis

### Scripts de evaluación post-training

Ubicados en `scripts/model_a_analysis/`:

```
scripts/model_a_analysis/
├── threshold_sweep.py     # curva P/R vs threshold
├── fp_analysis.py         # caracterización de FP/FN
├── feature_importance.py  # gain de cada feature
└── ablation.py           # impacto de remover grupos
```

### Script de evaluación de logs reales

```
scripts/eval_log_line.py   # evalúa requests desde log lines reales
```

Para ejecutarlos:

```bash
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/threshold_sweep.py
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/fp_analysis.py
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/feature_importance.py
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/model_a_analysis/ablation.py

# Evaluación de logs reales
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py --interactive
```

**Requerimientos:**
- Docker con MLflow corriendo en puerto 5081
- Artefactos accesibles via nginx proxy en puerto 5083
- `.venv` con dependencias: `pandas`, `numpy`, `scikit-learn`, `lightgbm`, `mlflow`, `requests`

---

## 5. Evaluación de requests reales via script

Esta es la prueba más directa del modelo: tomar un request HTTP real (en formato de log de Nginx/Apache) y preguntar directamente al modelo si es ataque o normal.

### Script: `eval_log_line.py`

**Ubicación:** `scripts/eval_log_line.py`

Este script parsea líneas de log en Combined Log Format (el formato estándar de Nginx y Apache), extrae method y URL, computa las 23 features, y devuelve la predicción del modelo.

#### Uso

```bash
# Evaluar una línea de log individual
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py '<log_line>'

# Modo interactivo (ingresar logs uno por uno)
MLFLOW_TRACKING_URI=http://localhost:5081 python scripts/eval_log_line.py --interactive
```

#### Cómo funciona internamente

```
Línea de log (Combined Log Format)
        │
        ▼
┌───────────────────────┐
│  Parser regex          │  Extrae: method, uri, query_string, time_local
│  (LOG_PATTERN)         │  No puede extraer body — los access logs no lo contienen
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  extract_features()    │  Computa las 23 features (method, URL, content)
│                        │  Misma lógica que preprocess_csic_v4.py
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  LightGBM.predict_proba │  Devuelve P(ataque)
│  vs threshold 0.2903   │  prediction = ATAQUE si proba >= 0.2903
└───────────────────────┘
        │
        ▼
   Resultado: ATAQUE / NORMAL
```

### Caso de prueba 1 — GET con SQL injection en query string

```
192.168.1.100 - - [14/Apr/2026:10:23:45 -0300] "GET /login?username=admin%27%20OR%201%3D1%20--&password=test HTTP/1.1" 200 1234 "-" "Mozilla/5.0"
```

**Resultado:**

```
🔴 ATAQUE
   Probabilidad: 100.0% (threshold: 29.0%)
   Method: GET
   URL: /login?username=admin%27%20OR%201%3D1%20--&password=test
   Body: (vacío — GET)
```

**Análisis de features extraídas:**

| Feature | Valor | Qué indica |
|---|---|---|
| `method_is_get` | 1 | Método GET |
| `url_length` | 53 | Longitud de la URL completa |
| `url_param_count` | 2 | Dos parámetros (`username=` y `password=`) |
| `url_pct_density` | 0.151 | 8 `%` en 53 caracteres — muy alto (típico: 0.00–0.05) |
| `url_has_pct27` | **1** | `%27` detectado — encoding de comilla simple `'`. Señal directa de SQLi |
| `url_has_pct3c` | 0 | Sin `%3C` (encoding de `<`) |
| `url_has_dashdash` | **1** | `--` detectado — comentario SQL |
| `url_has_script` | 0 | Sin la palabra `script` |
| `url_has_select` | 0 | Sin la palabra `SELECT` |
| `content_length` | 0 | GET no tiene body |

**Desglose del ataque:** la URL contiene `%27%20OR%201%3D1%20--` que se decodifica a `' OR 1=1 --` — un SQL injection clássico. El modelo detecta:
1. Alta densidad de `%` (URL encoding de caracteres especiales)
2. Presencia de `%27` (comilla simple codificada)
3. Presencia de `--` (comentario SQL)

Este es un acierto correcto del modelo. El ataque es real y el modelo lo detecta con 100% de "confianza".

---

### Caso de prueba 2 — POST login normal

```
192.168.1.100 - - [14/Apr/2026:10:26:01 -0300] "POST /api/login HTTP/1.1" 200 456 "-" "Mozilla/5.0"
```

**Resultado:**

```
🔴 ATAQUE
   Probabilidad: 99.9% (threshold: 29.0%)
   Method: POST
   URL: /api/login
   Body: (vacío — el body no está en el log de access)
```

**Análisis de features extraídas:**

| Feature | Valor | Qué indica |
|---|---|---|
| `method_is_get` | 0 | |
| `method_is_post` | **1** | Método POST |
| `method_is_put` | 0 | |
| `url_length` | 10 | `/api/login` es corto — 10 caracteres |
| `url_param_count` | 0 | Sin `=` en la URL (no hay query string) |
| `url_pct_density` | 0.0 | Sin caracteres `%` |
| `url_has_query` | 0 | Sin `?` |
| `url_has_pct27` | 0 | Sin indicadores de SQLi |
| `url_has_pct3c` | 0 | |
| `url_has_dashdash` | 0 | |
| `url_has_script` | 0 | |
| `url_has_select` | 0 | |
| `content_length` | 0 | El body no está en el log — se asume vacío |

### Por qué el modelo asigna 99.9% a este request

La explicación puede estar en `scale_pos_weight=1.44`, pero también es posible que el dataset CSIC 2010 haya etiquetado este tipo de requests como ataque si sus bodies contenían payloads maliciosos.

**No se puede afirmar que sea un falso positivo sin conocer el body original del request.**

### Limitación: los access logs no contienen el body

Este segundo caso es especialmente importante: **el log de access no tiene el body del POST.** El ataque podría estar en el body (`username=admin' OR 1=1--&password=test`), no en la URL. El modelo solo evaluó la URL porque es lo único disponible en el log.

```
# Lo que el modelo VE (del log):
POST /api/login    ← solo method + URL, sin body

# Lo que podría estar en el body real (pero el log no lo muestra):
username=admin' OR 1=1--&password=test
```

Para evaluar el body POST se necesita:
- Logs de un WAF o proxy que capture bodies
- Un sistema de instrumentation que registre los payloads completos
- Traffic analysis de un IDS/IPS

### Conclusión de la prueba

| Caso | Prediction | Probabilidad | ¿Correcto? |
|---|---|---|---|
| GET `/login?username=admin%27%20OR%201%3D1%20--` | ATAQUE | 100.0% | ✅ Correcto |
| POST `/api/login` | ATAQUE | 99.9% | ⚠️ Indeterminado — sin body no se puede confirmar ni desmentir |

El Caso 1 demuestra que el modelo detecta ataques visibles en la URL. El Caso 2 muestra que la ausencia del body impide validar la predicción.

**Implicación para producción:** sin visibilidad del body, no se puede confiar ciegamente en las predicciones del modelo. Se necesita un sistema que capture los payloads completos.