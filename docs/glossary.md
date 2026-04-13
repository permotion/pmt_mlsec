# Glosario

Definiciones y terminología usada en el proyecto. Ordenado alfabéticamente.

---

## A

**Align (pandas — alineación de columnas)**
Operación que sincroniza las columnas de dos DataFrames para que tengan exactamente las mismas columnas en el mismo orden. Necesario después de one-hot encoding en train y test por separado: el test puede tener categorías que no aparecieron en train (o viceversa), generando columnas distintas. `train.align(test, join='left', fill_value=0)` fuerza al test a tener exactamente las columnas del train, rellenando con 0 las que no tenía. Esto es crítico para que el modelo reciba el mismo número de features en entrenamiento e inferencia.

**Attack (label 1)**
Clase positiva en ambos modelos. Representa cualquier request o flujo de red identificado como malicioso. Ver también: *Malicious*, *label*.

---

## B

**Backend store (MLflow)**
Componente de almacenamiento donde MLflow persiste los metadatos de cada run: parámetros, métricas, tags, y ruta a los artefactos. En este proyecto usamos SQLite (`mlflow.db`) en la raíz del proyecto. El backend store se configura con el tracking URI al iniciar el servidor: `mlflow ui --backend-store-uri "sqlite:///mlflow.db"`. El file-based store (`mlruns/`) está deprecado en MLflow 3.x — no usar.

**Baseline (modelo baseline)**
El modelo más simple que se entrena primero, antes de probar alternativas más complejas. Sirve como punto de referencia: si un modelo más complejo no supera al baseline, no vale la pena usarlo. En este proyecto: Logistic Regression es el baseline de Modelo A, Random Forest es el baseline de Modelo B.

**Benign (label 0)**
Clase negativa. Tráfico legítimo, sin indicadores de ataque. Sinónimo de *Normal* en el contexto del Modelo A.

**Binary classification**
Tipo de problema ML donde el output es una de dos clases. En este proyecto: 0 (benign) o 1 (malicious).

---

## C

**Correlation (correlación)**
Medida estadística que indica cuánto varía una feature junto con el label. Valor entre -1 y 1. `+1` significa que cuando la feature sube, el label sube (más ataque). `-1` significa que cuando la feature sube, el label baja (más normal). `0` significa que no hay relación lineal. **Importante:** correlación baja con el label no significa que la feature sea inútil — modelos no-lineales como Random Forest pueden encontrar patrones que la correlación lineal no detecta.

**Cardinality (cardinalidad)**
Número de valores únicos de una columna categórica. Alta cardinalidad (ej: `proto` con 133 valores) es un problema para one-hot encoding porque genera demasiadas columnas. Estrategias para manejarla: top-N encoding (mantener los N más frecuentes + `other`), frequency encoding (reemplazar cada categoría por su frecuencia), o embeddings. En este proyecto usamos top-N para `proto`.

**Categorical dtype (pandas)**
Tipo de dato de pandas optimizado para columnas con pocos valores únicos repetidos (ej: `proto`, `service`, `state`). Internamente almacena los valores como enteros con un diccionario de mapeo, reduciendo el uso de memoria significativamente comparado con `object`. En UNSW-NB15 las categóricas ya vienen con este dtype en el parquet.

**CSIC 2010**
Dataset de requests HTTP generado por el Spanish National Research Council (CSIC). Contiene tráfico normal y ataques web (SQLi, XSS, CSRF, etc.). Usado para entrenar el Modelo A.

**Class imbalance**
Cuando una clase tiene muchos más ejemplos que la otra. En datasets de seguridad, los ataques suelen ser minoría. Afecta métricas y requiere estrategias como `class_weight='balanced'` o SMOTE.

**Confusion matrix**
Tabla de 2×2 que muestra cuántos registros cayeron en cada combinación de predicción real vs predicción del modelo. Es el punto de partida para calcular todas las métricas de clasificación.

```
                  Predicho: Normal   Predicho: Ataque
Real: Normal  →        TN                  FP
Real: Ataque  →        FN                  TP
```

- **TP** — ataque real, detectado como ataque ✅
- **TN** — tráfico normal, clasificado como normal ✅
- **FP** — tráfico normal, clasificado como ataque ❌ (falsa alarma)
- **FN** — ataque real, clasificado como normal ❌ (ataque no detectado — el error más costoso)

Ejemplo real — Random Forest baseline en CSIC 2010 (test set):

```
                  Predicho: Normal   Predicho: Ataque
Real: Normal  →       3.514              1.886
Real: Ataque  →         185              3.575
```

De esta matriz se derivan todas las métricas: `Recall = 3575 / (3575 + 185) = 0.951`, `Precision = 3575 / (3575 + 1886) = 0.655`. Ver también: *Recall*, *Precision*, *False Positive*, *False Negative*.

---

## D

**Data leakage (fuga de datos)**
Situación donde información del conjunto de test "se filtra" hacia el entrenamiento, produciendo métricas irrealmente optimistas que no se sostendrán en producción. El error más común: ajustar un scaler o encoder con todo el dataset (train + test) antes de dividir. La regla de oro: todo `fit` o `fit_transform` se hace **solo sobre el training set**. Luego se aplica `transform` al test. En `preprocess_unsw.py`: el `RobustScaler` se ajusta solo con `train` y se aplica con `transform` al `test`.

**DoS (Denial of Service)**
Ataque que busca agotar los recursos de un sistema (CPU, memoria, ancho de banda) para dejarlo inaccesible a usuarios legítimos. En UNSW-NB15 representa el 10.3% de los ataques. Se detecta por features de volumen: alto `sbytes`, `dbytes`, `rate`, `spkts`.

**dtype (data type)**
Tipo de dato de cada columna en un DataFrame de pandas. Determina cómo se almacena en memoria y qué operaciones se pueden hacer. Los más comunes en este proyecto: `int8/16/32/64` (enteros), `float32/64` (decimales), `object` (texto), `category` (categórico optimizado), `bool`. Elegir el dtype correcto impacta directamente en el uso de memoria — `float32` usa la mitad de memoria que `float64`.

**DAG (Directed Acyclic Graph)**
Estructura de Airflow que define las tareas de un pipeline y sus dependencias. En este proyecto: `ingest → preprocess → train → evaluate → register`.

**Decision threshold**
Valor entre 0 y 1 que convierte la probabilidad que predice el modelo en una clasificación binaria (0 o 1). Si la probabilidad de un request es mayor o igual al threshold → se clasifica como ataque.

El threshold por defecto en scikit-learn es 0.5, pero ese valor asume que los errores FP y FN tienen el mismo costo. En seguridad no es así — un FN (ataque no detectado) es más costoso que un FP (falsa alarma). El threshold se optimiza buscando el valor que cumple Recall ≥ 0.95 con la mayor Precision posible, evaluado sobre el **val set**.

Resultado en el baseline de CSIC 2010:

| Modelo | Threshold óptimo | Efecto si se usara 0.5 |
|---|---|---|
| Random Forest | **0.15** | Recall caería — demasiado conservador |
| Logistic Regression | ~0.30 | Aún así clasifica todo como ataque — ROC-AUC 0.76 no tiene capacidad real |

Un threshold muy bajo (0.15) indica que el modelo no está muy seguro de sus predicciones — clasifica como ataque apenas ve una probabilidad de 15%. Esto es consecuencia del desbalance de clases y del criterio de Recall prioritario. Ver también: *Precision vs Recall — trade-off*, *Confusion matrix*.

---

## E

**Estado ✅ / ❌ (criterio MVP)**
Iconos usados en las tablas de resultados para indicar si un modelo cumple o no cada criterio del MVP, de forma **independiente por métrica**:

- **✅** — la métrica cumple o supera el mínimo definido
- **❌** — la métrica no cumple el mínimo

Se usan de forma independiente porque Recall y Precision son criterios **separados con distinto peso**: Recall ≥ 0.95 es prioritario (si falla, el modelo no detecta ataques), Precision ≥ 0.85 es el objetivo secundario (si falla, genera demasiadas falsas alarmas). Un modelo puede cumplir uno y no el otro.

Ejemplo — Random Forest baseline: `Recall ✅ Precision ❌` significa: detecta correctamente el 95.1% de los ataques (Recall cumplido), pero de las 5.461 alarmas que dispara, 1.886 son falsas (Precision 0.655 — muy por debajo de 0.85). El modelo es seguro en el sentido de no dejar pasar ataques, pero genera demasiado ruido para ser operable en producción.

Un run donde ambas métricas muestran ✅ cumple todos los criterios MVP y puede pasar al model registry. En este proyecto, ningún modelo ha alcanzado ese estado todavía. Ver también: *Recall*, *Precision*, *Decision threshold*.

**Experiment (experimento ML)**
Iteración sobre un modelo o sus features a partir de un resultado insatisfactorio. Se parte de una hipótesis ("si agrego esta feature, la Precision debería mejorar"), se implementa el cambio, y se miden las métricas para confirmar o refutar la hipótesis. Se diferencia del EDA en que el EDA explora los datos sin un modelo previo, mientras que el experimento itera sobre un modelo ya entrenado con resultados conocidos. En este proyecto los experimentos viven en `notebooks/experiments/` y se registran en `docs/experiments.md`.

**Exploit**
Técnica de ataque que aprovecha una vulnerabilidad conocida en software o hardware. En UNSW-NB15 representa el 28% de los ataques — la segunda categoría más frecuente. A diferencia del fuzzing (que busca vulnerabilidades desconocidas), un exploit tiene un objetivo específico y un CVE conocido.

**EDA (Exploratory Data Analysis)**
Análisis inicial de un dataset para entender su estructura, distribuciones, nulos y relaciones entre variables. Se hace en Jupyter Notebooks antes de construir el pipeline.

---

## F

**Feature**
Una columna del dataset de entrada que el modelo usa para hacer su predicción. En este proyecto, ninguna feature existe tal cual en el dataset crudo — todas se construyen en el preprocessing a partir de los datos originales.

**Cómo se define una feature — 4 pasos:**

1. **Identificar la señal** — en el EDA o en el análisis de FP se observa un patrón (ej: los ataques tienen URLs con chars percent-encoded; el tráfico normal tiene paths más profundos en la URL)
2. **Transformar el dato crudo** — definir qué operación se aplica sobre qué columna (ej: `url.str.contains('%27')`, `url.str.len()`, `url.str.count('/')`)
3. **Validar la señal** — calcular la correlación con el label, en la subpoblación relevante si corresponde
4. **Decidir** — si la correlación es significativa y el impacto en métricas es positivo, se incorpora al preprocessing oficial

**Tipos de features en este proyecto:**

| Tipo | Ejemplo | Cómo se calcula |
|---|---|---|
| Binaria (0/1) | `url_has_pct27` | `url.str.contains('%27').astype('int8')` |
| Entera | `url_length` | `url.str.len().astype('int32')` |
| Float | `url_pct_density` | `url.str.count('%') / url.str.len().clip(lower=1)` |
| One-hot | `method_is_get` | `(method == 'GET').astype('int8')` |

Ver también: *Feature engineering*, *Feature importance*, *Preprocessing exploratorio*, *Subpoblación*.

**Feature ceiling (techo de features)**
Situación donde múltiples algoritmos distintos alcanzan el mismo nivel de performance, indicando que el cuello de botella no es el modelo sino la información disponible en las features. En Modelo A (CSIC 2010): LR, RF, XGBoost y LightGBM todos se estancan en ~0.94 ROC-AUC. Cuando esto ocurre, cambiar de algoritmo no mejora los resultados — hay que agregar features nuevas o mejorar las existentes.

**False Positive analysis (análisis de falsos positivos)**
Técnica de diagnóstico que examina qué características tienen en común los registros mal clasificados como positivos (FP). Permite entender por qué el modelo confunde tráfico legítimo con ataques. En Modelo A: los 1.886 FP no tienen ningún indicador de payload (`url_has_*` = 0) — el modelo los clasifica como ataque únicamente por tener URLs o bodies más largos. Esto orientó la creación de `url_pct_density` para dar contexto a la longitud.

**False Positive rate (FPR)**
Proporción de tráfico normal que el modelo clasifica incorrectamente como ataque. `FPR = FP / (FP + TN)`. Una FPR alta significa muchas falsas alarmas — el analista de seguridad recibe alertas que no son reales. Complementario a la Precision: `Precision = TP / (TP + FP)`, una Precision baja implica FPR alta.

**fit / fit_transform / transform (scikit-learn)**
Patrón estándar de scikit-learn para transformaciones que aprenden parámetros de los datos:
- `fit(X_train)` — aprende los parámetros (ej: mediana e IQR del RobustScaler) **solo del training set**
- `transform(X)` — aplica la transformación aprendida a cualquier conjunto
- `fit_transform(X_train)` — atajo que hace fit + transform en un solo paso, solo para train

Nunca usar `fit_transform` en el test set — eso sería data leakage. En `preprocess_unsw.py`: `scaler.fit_transform(train)` aprende la escala del train, `scaler.transform(test)` aplica esa misma escala al test.

**Feature cross (feature cruzada)**
Feature que combina dos señales existentes multiplicándolas o combinándolas lógicamente. Ejemplo: `post_has_pct27 = method_is_post AND url_has_pct27`. Captura patrones que ninguna de las dos features sola puede capturar. En este proyecto `post_has_pct27` resultó NaN — no había intersección suficiente en el dataset para generar señal.

**Feature iteration (iteración de features)**
Proceso de agregar, modificar o eliminar features a partir del análisis de los errores del modelo. Pasos típicos: (1) feature importance para identificar qué features aportan y cuáles son ruido, (2) análisis de falsos positivos/negativos para entender qué patrones el modelo no puede distinguir, (3) construir features nuevas que capturen esa señal faltante, (4) medir el impacto en las métricas. En este proyecto: iteración 1 en `notebooks/experiments/csic2010_feature_analysis.ipynb`.

**Feature redundancy (redundancia de features)**
Situación donde dos o más features contienen casi la misma información. Se detecta con el coeficiente de correlación de Pearson entre features. Si dos features tienen correlación > 0.9, generalmente se puede descartar una sin perder capacidad predictiva. En UNSW-NB15: `swin`/`dwin` (0.99), `dpkts`/`dloss` (0.98). Reducir redundancias simplifica el modelo sin sacrificar performance.

**Fuzzer / Fuzzing**
Técnica de ataque que envía input malformado, aleatorio o inesperado a un sistema para encontrar bugs, crashes o vulnerabilidades. Un fuzzer genera miles de variaciones de requests. En UNSW-NB15 representa el 15.2% de los ataques. Los fuzzers generan patrones de tráfico con alta variabilidad en `sbytes` y número de paquetes.

**F1 Score**
Media armónica de Precision y Recall. Resume ambas métricas en un solo número.

`F1 = 2 × (Precision × Recall) / (Precision + Recall)`

A diferencia de la media aritmética, la media armónica penaliza fuertemente cuando una de las dos métricas es baja. Un modelo con Recall 0.977 y Precision 0.417 tiene F1 = 0.584 — lejos del 1.0, aunque el Recall sea alto.

**Cuándo usarlo:** cuando no hay prioridad clara entre Precision y Recall (ej: Modelo B — UNSW-NB15, donde el criterio es F1 ≥ 0.88). **Cuándo NO usarlo como criterio principal:** cuando las métricas tienen pesos distintos — como en Modelo A, donde Recall ≥ 0.95 es no negociable y Precision ≥ 0.85 es el objetivo secundario. En ese caso, F1 puede enmascarar que un modelo cumple uno de los dos criterios pero no el otro. Se loggea en cada run para referencia, pero no es la métrica de decisión en Modelo A.

**False Negative (FN)**
El modelo predijo *benign* pero era un ataque. En seguridad, el error más costoso.

**False Positive (FP)**
El modelo predijo *attack* pero era tráfico legítimo. Genera alertas innecesarias.

**Feature engineering**
Proceso de crear o transformar variables a partir de los datos crudos para mejorar el desempeño del modelo. En CSIC 2010: convertir la URL cruda en indicadores binarios como `url_has_pct27` o `url_length`. Las features no existen en el dataset original — se construyen a partir de él.

**Feature importance**
Medida de cuánto contribuye cada feature a las predicciones del modelo. En árboles de decisión y Random Forest, se puede calcular directamente. Permite identificar qué variables tienen más poder discriminativo y descartar las que no aportan.

**False Negative rate (FNR)**
Proporción de ataques reales que el modelo no detectó. `FNR = FN / (FN + TP)`. Complementario al Recall: `FNR = 1 - Recall`. En seguridad, minimizar el FNR es prioritario.

---

## L

**Label**
Valor de la variable objetivo.

**LightGBM (Light Gradient Boosting Machine)**
Variante de Gradient Boosting desarrollada por Microsoft, optimizada para velocidad y eficiencia de memoria. Construye árboles de forma leaf-wise (crece por las hojas con mayor ganancia) en lugar de level-wise como XGBoost. Más rápido en datasets grandes. Hiperparámetro clave: `scale_pos_weight` para desbalance.

Usado en: **Modelo A (CSIC 2010)**. Resultado: ROC-AUC 0.941 (mejor ROC-AUC del grupo), Recall 0.953 ✅, Precision 0.654 ❌ — resultados casi idénticos a Random Forest.
Pendiente en: **Modelo B (UNSW-NB15)** — todavía no entrenado.

**Logistic Regression (regresión logística)**
Modelo de clasificación lineal que estima la probabilidad de que una muestra pertenezca a la clase positiva. A pesar del nombre, es un clasificador. Calcula una combinación lineal de las features y la pasa por una función sigmoide para obtener una probabilidad entre 0 y 1. Es el modelo más simple para clasificación — sirve como baseline. Sus limitaciones: no captura relaciones no-lineales entre features.

Usado en: **Modelo A (CSIC 2010)** como baseline. Resultado: ROC-AUC 0.761, predice todo como ataque — Precision 0.411 ❌. Descartado. En este proyecto: `0` = benign, `1` = malicious. Consistente en ambos modelos.

---

## M

**Modelos evaluados — resumen por dataset**

| Modelo | Modelo A (CSIC 2010) | Modelo B (UNSW-NB15) |
|---|---|---|
| Logistic Regression | ✅ ejecutado — ROC-AUC 0.761 ❌ descartado | — |
| Random Forest | ✅ ejecutado — ROC-AUC 0.939, Recall ✅ Precision ❌ | 🔄 pendiente (será baseline) |
| XGBoost | ✅ ejecutado — ROC-AUC 0.933, Recall ✅ Precision ❌ | 🔄 pendiente |
| LightGBM | ✅ ejecutado — ROC-AUC 0.941, Recall ✅ Precision ❌ | 🔄 pendiente |

Todos los modelos de Modelo A cumplen Recall ≥ 0.95 pero ninguno alcanza Precision ≥ 0.85. El cuello de botella son las features, no el algoritmo — todos llegan al mismo techo de ~0.94 ROC-AUC.

**Machine Learning model (modelo ML)**
Algoritmo que aprende patrones a partir de datos de entrenamiento para hacer predicciones sobre datos nuevos. En clasificación binaria: aprende a distinguir entre dos clases (ej: normal vs ataque). El modelo no programa reglas explícitas — las infiere de los ejemplos. Tres componentes clave: **arquitectura** (qué tipo de modelo), **parámetros** (lo que aprende durante el training), e **hiperparámetros** (configuración que se fija antes de entrenar, ej: `n_estimators` en Random Forest).

**Malware**
Software malicioso diseñado para dañar, acceder sin autorización, o comprometer sistemas. En UNSW-NB15 aparece como subcategorías: Backdoor (acceso remoto oculto), Shellcode (ejecución de código arbitrario), Worms (auto-propagación en red). Juntos representan solo el 2.5% de los ataques en el dataset — el modelo va a tener pocos ejemplos de estos patrones.

**Malicious (label 1)**
Sinónimo de *Attack* en el contexto del Modelo B (UNSW-NB15).

**MLflow**
Plataforma de experiment tracking. Registra parámetros, métricas y artefactos de cada run de entrenamiento. Los tres conceptos clave son: **Experiment** (agrupa runs del mismo modelo), **Run** (una ejecución individual con su metadata completa), y **Backend store** (donde se persiste todo — en este proyecto, SQLite). Primera integración en el proyecto: `csic2010_feature_analysis_v3.ipynb`. Para levantar la UI: `mlflow ui --backend-store-uri "sqlite:///mlflow.db"` → http://localhost:5000.

**MLflow Experiment**
Agrupador lógico de runs del mismo modelo o familia de experimentos. En este proyecto hay un experiment por modelo: `mlsec-model-a` (CSIC 2010) y `mlsec-model-b` (UNSW-NB15). Todos los runs de un mismo modelo van al mismo experiment, lo que permite comparar iteraciones directamente en la UI.

**Model registry**
Componente de MLflow donde se guardan los modelos que superaron los criterios de éxito, listos para inferencia.

---

## I

**IQR (Interquartile Range — rango intercuartil)**
Diferencia entre el percentil 75 (P75) y el percentil 25 (P25) de una distribución. `IQR = P75 - P25`. Mide la dispersión del 50% central de los datos, ignorando los extremos. Es resistente a outliers — un valor extremo no lo distorsiona. Usado por `RobustScaler` como denominador de la normalización: `(x - mediana) / IQR`.

**Imbalanced classes** → ver *Class imbalance*.

---

## N

**NaN (Not a Number)**
Valor faltante en pandas/numpy. En CSIC 2010, `content` y `lenght` son NaN en requests GET — no es un error de datos sino el comportamiento esperado del protocolo HTTP (los GETs no tienen body). Distinguir entre NaN estructural (esperado) y NaN por error de datos es una tarea del EDA.

**Normal (label 0)**
Sinónimo de *Benign* en el contexto del Modelo A (CSIC 2010).

---

## O

**Ordinal encoding**
Alternativa a one-hot encoding para variables categóricas. Asigna un número entero a cada categoría (ej: tcp=0, udp=1, arp=2). Más compacto que one-hot pero introduce un orden artificial que puede confundir al modelo (¿tcp < udp?). Útil para árboles de decisión que no son sensibles al orden, pero problemático para modelos lineales.

**Outlier**
Valor extremo que se aleja significativamente de la distribución del resto de los datos. En features de red como `sbytes` o `dur`, es común encontrar outliers por conexiones anómalas o ataques volumétricos. Los outliers pueden distorsionar modelos lineales y la normalización — se detectan con boxplots e IQR, y se tratan con clipping o transformaciones logarítmicas.

**One-hot encoding**
Técnica para convertir una variable categórica en múltiples columnas binarias. Ejemplo: la columna `Method` con valores GET/POST/PUT se convierte en tres columnas: `method_is_get`, `method_is_post`, `method_is_put`. Cada fila tiene exactamente un `1` y el resto `0`. Necesario para que los algoritmos ML puedan procesar variables categóricas.

**Offline detection**
Modalidad de detección donde el modelo evalúa logs o tráfico ya capturado, sin bloquear en tiempo real. Es el modo del MVP.

---

## P

**Protocol (proto)**
En redes, el protocolo de transporte usado por una conexión. Los más comunes en UNSW-NB15: `tcp` (orientado a conexión, confiable), `udp` (sin conexión, más rápido pero sin garantías), `arp` (resolución de direcciones IP a MAC). La columna `proto` tiene 133 valores únicos — se reduce a top-10 + `other` para el modelo.

**Parquet**
Formato de archivo columnar binario, optimizado para análisis de datos. Más eficiente que CSV: compresión nativa, preserva dtypes (incluido `category`), lectura mucho más rápida. UNSW-NB15 viene en parquet — por eso los dtypes ya están correctos al cargarlo. En pipelines ML se prefiere sobre CSV para datos procesados.

**Percent-encoding (URL encoding)**
Mecanismo para representar caracteres especiales en una URL o body HTTP usando el formato `%XX` donde XX es el código hexadecimal del carácter. Ejemplos: `'` → `%27`, `<` → `%3C`, `>` → `%3E`, `;` → `%3B`. En el EDA de CSIC 2010 se descubrió que los atacantes siempre usan percent-encoding para evadir filtros — los chars literales nunca aparecen en las URLs del dataset.

**Percent-encoding — Latin-1 vs ataque**
Distinción crítica descubierta en el análisis de FP de v6: no todo `%XX` es sospechoso. Existen dos categorías con significado radicalmente distinto:

| Categoría | Rango hex | Ejemplos concretos | Quién lo usa |
|---|---|---|---|
| **Ataque** | `%00`–`%3F` | `%27`=`'`, `%3C`=`<`, `%3E`=`>`, `%3B`=`;` | SQLi, XSS, path traversal |
| **Latin-1 inofensivo** | `%C0`–`%FF` | `%F1`=`ñ`, `%ED`=`í`, `%FA`=`ú`, `%E1`=`á`, `%F3`=`ó` | Texto español/europeo en formularios normales |

**El problema en CSIC 2010:** la feature `content_pct_density` cuenta todos los `%XX` por igual. Un formulario español con `apellidos=Murgu%EDa` o `password=lIMpi%24a%FA%F1as` tiene alta densidad de `%` — pero son vocales acentuadas, no payloads de inyección. El modelo los clasifica como ataque porque ve la misma señal que en `%27%20OR%201%3D1`.

**¿Por qué los ataques nunca usan Latin-1?**

Tres razones técnicas:

1. **El payload tiene que ser interpretado como código.** Para que `' OR 1=1--` funcione como SQLi, el parser SQL del servidor tiene que leer esa cadena como sintaxis SQL válida. Un parser SQL no espera `ñ` — si el payload incluye `%F1`, el parser probablemente falla o ignora el contenido antes del carácter inválido. El atacante pierde control del payload.

2. **Los atacantes usan payloads mínimos y precisos.** Un payload efectivo es `' OR 1=1--` — nada más. Caracteres innecesarios aumentan el riesgo de que un WAF rechace el request o que el servidor falle al parsear. El encoding Latin-1 no aporta nada al ataque y solo añade ruido.

3. **El encoding Latin-1 puede corromper el payload.** Si el servidor interpreta el body como ASCII o UTF-8, un `%F1` puede corromper el string completo dependiendo del encoding esperado. Un atacante experimentado no mezcla encodings.

**¿Un ataque con ñ tendría más chances de éxito?** No — al revés. Más caracteres innecesarios = más ruido = más chances de detección o rechazo. Los payloads de inyección exitosos son quirúrgicos.

**La asimetría práctica:** en el dataset CSIC 2010, cero ataques tienen `%F1` o `%ED` en su payload. El 100% de los requests con `%F1` son formularios legítimos con nombres españoles. Esta separación perfecta en la práctica es la señal que `content_pct_latin1_density` y `url_pct_latin1_density` buscan capturar en v7.

**Caso borde:** apellidos como `D'Amico` → `D%27Amico` usan `%27` legítimamente (apóstrofe en nombre propio). Son 8 FP sobre 938 (0.9%) — inevitables con features de texto sin análisis de contexto semántico. Ver también: *Percent-encoding*, *False Positive*, *content_pct_density*.

**Power discriminativo**
Capacidad de una feature para separar clases. Una feature con alto poder discriminativo tiene distribuciones muy distintas entre la clase 0 y la clase 1. En CSIC 2010: `method_is_put` tiene poder discriminativo perfecto (100% de los PUT son ataques).

**Preprocessing**
Etapa del pipeline donde los datos crudos se transforman en features listas para el modelo. Incluye: eliminar columnas irrelevantes, encodear categóricas, normalizar numéricas, manejar nulos, y construir nuevas features. Es la implementación en script de las decisiones tomadas en el EDA. Ver también: *Preprocessing exploratorio*.

**Preprocessing exploratorio**
Código de construcción de features que vive **dentro de un notebook de experimento**, no en un script oficial. Su objetivo es probar una feature candidata en memoria antes de comprometerse a incorporarla al pipeline.

Características clave:
- No genera ningún archivo a disco — las features existen solo mientras corre el notebook
- Si la feature no tiene señal, se descarta sin rastro en el código oficial
- Si hay señal (paso 7 del flujo exploratorio), el código del notebook sirve de referencia para escribir el `preprocess_csic_vN.py`

**Diferencia con Preprocessing oficial:**

| | Oficial (`src/mlsec/data/preprocess_csic_vN.py`) | Exploratorio (dentro del notebook) |
|---|---|---|
| Output | Parquet estable en `data/processed/` | Nada — solo en memoria |
| Reproducible | Sí | Solo en el contexto del notebook |
| Descartable | No | Sí — si no hay señal |

Ver también: *Preprocessing*, *Feature*, *Subpoblación*, *Experimentos — Preprocessing oficial vs Preprocessing exploratorio*.

**Precision**
De todos los que el modelo predijo como ataque, ¿cuántos realmente lo eran?
`Precision = TP / (TP + FP)`

Ejemplo: el modelo disparó 150 alarmas. Solo 95 eran ataques reales → Precision = 95/150 = 0.63. Las 55 alarmas de más son Falsos Positivos — tráfico normal clasificado como ataque. Una Precision baja inunda al analista de seguridad con alertas falsas. Criterio mínimo Modelo A: **Precision ≥ 0.85**. Ver también: *Precision vs Recall — trade-off*.

**Pipeline**
Secuencia de pasos de transformación y modelado. En este proyecto: ingest → preprocess → train → evaluate → register.

---

## R

**Random Forest**
Modelo de ensemble que construye múltiples árboles de decisión **en paralelo**, cada uno sobre una muestra aleatoria del dataset. Es el segundo modelo evaluado en Modelo A y será el baseline de Modelo B.

**Cómo funciona — 3 mecanismos clave:**

**1. Bootstrap sampling (bagging)**
Cada árbol se entrena sobre una muestra con reemplazo del dataset. Si hay 10.000 filas, cada árbol ve ~6.300 filas distintas (el ~63.2% estadístico del muestreo con reemplazo). Las filas no seleccionadas se usan para el "out-of-bag error" — validación gratuita sin necesidad de un val set separado. Esto hace que los árboles sean distintos entre sí, aunque todos usen el mismo dataset.

**2. Random feature subsets**
En cada nodo de cada árbol, solo se evalúa un subconjunto aleatorio de features para decidir la división. Por defecto en clasificación: `max_features = sqrt(n_features)`. Con 22 features → cada nodo evalúa ~4-5 features al azar. Esto fuerza diversidad: ningún árbol puede depender siempre de las features más fuertes, lo que reduce el sobreajuste.

**3. Promedio de probabilidades**
La predicción final es el **promedio** de las probabilidades de todos los árboles. Un árbol aislado puede memorizar el training set (alta varianza). El promedio de 200 árboles con distintos datos y distintas features tiende a cancelar esos errores individuales y generaliza mejor.

**Por qué es mejor que un solo árbol de decisión:**
Un árbol individual tiene alta varianza — memoriza el training set pero falla en datos nuevos. Random Forest reduce esa varianza promediando muchos árboles distintos, sin sacrificar la capacidad de capturar relaciones no-lineales.

**Por qué es mejor que Logistic Regression para este problema:**
LR asume que la frontera de decisión es lineal — que cada feature contribuye de forma independiente y aditiva. Los ataques web no siguen ese patrón: una URL larga *sin* indicadores de payload es tráfico normal; larga *con* `%27` es ataque. La combinación importa. RF captura esas interacciones sin que se construyan features cruzadas manualmente.

**Hiperparámetros clave en este proyecto:**

| Parámetro | Valor | Por qué |
|---|---|---|
| `n_estimators` | 200 | 200 árboles — suficiente para estabilidad, sin rendimientos decrecientes notables |
| `class_weight='balanced'` | automático | Compensa el desbalance 59/41 — penaliza más los errores en la clase minoritaria |
| `max_features` | `'sqrt'` (default) | Subconjunto aleatorio en cada nodo — fuerza diversidad entre árboles |
| `random_state` | 42 | Reproducibilidad — mismo resultado en cada ejecución |
| `n_jobs` | -1 | Usa todos los cores disponibles — los árboles se construyen en paralelo |

**Resultados en Modelo A (CSIC 2010):**

| Versión | ROC-AUC | Recall | Precision | FP |
|---|---|---|---|---|
| Baseline (15 features) | 0.939 | 0.951 ✅ | 0.655 ❌ | 1886 |
| v4 (22 features) | 0.961 | 0.949 ❌ | 0.779 ❌ | 1011 |

Pendiente en: **Modelo B (UNSW-NB15)** como baseline — todavía no entrenado. Ver también: *Feature importance*, *class_weight='balanced'*, *XGBoost*, *LightGBM*, *Decision threshold*.

**RobustScaler**
Normalizador de scikit-learn que usa la mediana y el IQR (rango intercuartil) en lugar de la media y la desviación estándar. Resistente a outliers — los valores extremos no distorsionan la escala. Fórmula: `(x - mediana) / IQR`. Estrategia elegida para UNSW-NB15 dado los outliers extremos en features como `sbytes`, `sload`, `sjit`.

**Reconnaissance**
Fase de un ataque donde el atacante escanea y recopila información sobre el objetivo — puertos abiertos, servicios activos, versiones de software. No causa daño directo pero es precursor de ataques más severos. En UNSW-NB15 representa el 8.8% de los ataques. Se detecta por patrones de escaneo: muchos paquetes pequeños hacia distintos puertos.

**Recall (Sensitivity)**
De todos los ataques reales, ¿cuántos detectó el modelo?
`Recall = TP / (TP + FN)`

Ejemplo: hay 100 ataques reales. El modelo detecta 95 → Recall = 0.95. Los 5 no detectados son Falsos Negativos — ataques que pasaron sin alarma. En seguridad es la métrica más importante porque un ataque no detectado es peor que una falsa alarma. Criterio mínimo Modelo A: **Recall ≥ 0.95**.

**Precision vs Recall — trade-off**
No se pueden maximizar ambas métricas al mismo tiempo con el mismo modelo. Si bajás el threshold para detectar más ataques (↑ Recall), inevitablemente clasificás más tráfico normal como ataque (↓ Precision). Si subís el threshold para reducir falsas alarmas (↑ Precision), dejás pasar más ataques (↓ Recall). La curva Precision-Recall visualiza este trade-off en todos los thresholds posibles. El threshold óptimo se elige según qué error tiene mayor costo — en seguridad, el FN (ataque no detectado) es más costoso que el FP (falsa alarma).

**ROC-AUC**
Área bajo la curva ROC (Receiver Operating Characteristic). Mide la capacidad del modelo de **separar clases en todos los thresholds posibles** — no en un threshold específico. Valor entre 0.5 (aleatorio, sin capacidad de separación) y 1.0 (separación perfecta).

La ventaja frente a Recall o Precision es que es independiente del threshold: dos modelos pueden tener el mismo ROC-AUC y muy distintos Recall/Precision si usan thresholds diferentes.

Referencia de interpretación para este proyecto:

| Valor | Interpretación |
|---|---|
| 0.5 | Aleatorio — el modelo no aprende nada |
| 0.77 | Débil — Logistic Regression en CSIC 2010. No puede separar las clases con estas features |
| 0.93–0.94 | Baseline — RF/XGBoost/LightGBM con 15 features (v1) |
| 0.95–0.955 | v2/v3 — los mismos modelos con 17-19 features. Techo que se mantuvo hasta v3 |
| 0.966 | v4 — LightGBM con 22 features. Primer modelo en romper el plateau |
| 1.0 | Perfecto — no realista en la práctica |

Un modelo con ROC-AUC 0.777 (Logistic Regression) tiene capacidad de separación muy limitada — aunque su Recall sea 0.977, lo logra clasificando casi todo como ataque (Precision 0.417). El ROC-AUC bajo delata que no distingue bien, solo baja el threshold al mínimo. Ver también: *Decision threshold*.

**Run (MLflow)**
Una ejecución individual de entrenamiento, identificada por un UUID único (run ID). Contiene: parámetros loggeados (`mlflow.log_param`), métricas (`mlflow.log_metric`), artefactos como plots y el modelo serializado (`mlflow.log_artifact`), y metadata de sistema (duración, estado, fecha). Los runs se agrupan dentro de un Experiment. Naming convention en este proyecto: `model-a-{algoritmo}-features-{versión}` (ej: `model-a-rf-features-v3`).

---

## S

**Subpoblación (subpopulation analysis)**
Técnica de análisis que evalúa una feature o un modelo exclusivamente dentro de un subconjunto relevante del dataset, en lugar de sobre toda la población. Evita el "ruido de dilución" que ocurre cuando se calcula correlación en toda la muestra incluyendo casos donde la feature no tiene significado. Ejemplo clave en este proyecto: `content_pct_density` se analiza solo en los 17.580 requests POST (donde el body tiene significado real), no en los 36.000 totales (donde los GETs tienen content vacío). La correlación en POSTs es 0.406 vs 0.279 en la población completa — la señal es mucho más clara cuando se filtra el ruido estructural. Esta técnica también se aplica al análisis de FP: separar qué proporción son GETs (62.2%) vs POSTs (37.8%) define el techo teórico de cualquier feature de content.

**Skewed distribution (distribución sesgada)**
Distribución asimétrica donde la mayoría de los valores están concentrados en un extremo con una cola larga hacia el otro lado. En UNSW-NB15, features como `sbytes`, `sload` y `dur` son altamente skewed a la derecha — la mayoría de conexiones tienen valores bajos pero algunas tienen valores extremadamente altos. Requiere RobustScaler o transformación logarítmica antes de usarlas en modelos lineales.

**Sparse feature**
Feature que tiene valor 0 (o nulo) para la gran mayoría de los registros y solo activa en casos específicos. En UNSW-NB15: `is_ftp_login`, `trans_depth`, `tcprtt` tienen mediana=0 y P75=0 — solo son relevantes para conexiones FTP o TCP específicas. Son útiles igual: cuando activan, suelen ser muy discriminativas.

**StandardScaler**
Normalizador que transforma cada feature para tener media=0 y desviación estándar=1. Fórmula: `(x - media) / std`.

Se usa cuando features numéricas continuas conviven con features binarias (0/1). Sin escalar, un modelo lineal le daría más peso a las continuas simplemente por tener valores más grandes — no porque sean más importantes. Ejemplo en CSIC 2010: `url_length` va de 0 a 400, `url_has_pct27` solo vale 0 o 1. StandardScaler lleva `url_length` al mismo rango de magnitud que las binarias.

**Regla crítica:** el `fit` (aprendizaje de media y std) se hace **solo sobre el train set**. Luego se aplica `transform` con esos mismos números a val y test. Si se hiciera `fit` en val o test, el scaler usaría información de datos que el modelo no debería haber visto — data leakage.

**Cuándo NO usarlo:** features con outliers extremos como `sbytes` o `sload` en UNSW-NB15 — un valor máximo de 12M distorsiona la media y hace que el scaler sea inútil. En esos casos usar `RobustScaler` (usa mediana e IQR en lugar de media y std). Ver también: *RobustScaler*, *Data leakage*, *fit / fit_transform / transform*.

**class_weight='balanced'**
Parámetro de scikit-learn que ajusta automáticamente los pesos de cada clase inversamente proporcional a su frecuencia. Penaliza más los errores en la clase minoritaria. Alternativa más simple que SMOTE para desbalances leves. En CSIC 2010 (59/41) es la estrategia elegida.

**SMOTE (Synthetic Minority Oversampling Technique)**
Técnica para balancear clases cuando el desbalance es moderado-alto (ej: 70/30 o peor). Genera ejemplos **sintéticos** de la clase minoritaria interpolando entre ejemplos reales existentes — no duplica, crea nuevos puntos en el espacio de features.

**Cuándo usarlo:** cuando `class_weight='balanced'` no alcanza, típicamente con desbalances mayores al 65/35.

**Regla crítica:** SMOTE **solo se aplica al training set**, nunca al val ni al test. Aplicarlo en val/test contaminaría la evaluación con datos artificiales y daría métricas irreales.

**Por qué se usa en ML de seguridad:** los ataques suelen ser minoría en tráfico real. Si el modelo ve 95% de ejemplos normales, aprende a predecir "normal" siempre y logra 95% de accuracy sin detectar nada. SMOTE balancea el training para que el modelo aprenda ambas clases correctamente.

**Split train/test**
División del dataset en dos subsets con roles distintos:

- **Train set:** datos con los que el modelo **aprende**. Ve los ejemplos, ajusta sus parámetros internos, aprende los patrones.
- **Validation set (val):** datos que el modelo **no vio durante el training**. Se usa para ajustar hiperparámetros y tomar decisiones de diseño (qué modelo usar, qué threshold aplicar).
- **Test set:** datos que el modelo **nunca vio**. Solo se usa al final para reportar las métricas reales del MVP. Si se usa antes, las métricas quedan sesgadas.

En este proyecto el split es **70% train / 15% val / 15% test**, estratificado (preserva la proporción de clases en cada subset). UNSW-NB15 tiene un split predefinido en los archivos parquet — se respeta ese split oficial.

**Por qué separar:** si evaluás el modelo con los mismos datos con los que entrenó, va a parecer perfecto aunque no generalice. El test set simula datos del mundo real que el modelo nunca vio.

**Stratified split**
División del dataset que preserva la proporción de clases en cada subset (train/val/test). Necesario con clases desbalanceadas. Sin estratificación, un subset podría quedar con casi todos los ataques y otro con casi ninguno, haciendo la evaluación poco representativa.

---

## T

**True Positive (TP)**
El modelo predijo *attack* y era realmente un ataque. Detección correcta.

**True Negative (TN)**
El modelo predijo *benign* y era realmente tráfico legítimo. Clasificación correcta de la clase negativa.

---

## T

**Tracking URI (MLflow)**
URI que MLflow usa para encontrar el backend store donde persiste los runs. Se configura con `mlflow.set_tracking_uri(uri)` antes de iniciar cualquier run. Para SQLite con path absoluto, el formato es `sqlite:////ruta/absoluta/al/archivo.db` (4 barras). Una trampa común: SQLAlchemy no URL-decodea `%20`, por lo que rutas con espacios deben pasarse literales — `sqlite:////Users/foo/PMT MLSec/mlflow.db` funciona, `sqlite:////Users/foo/PMT%20MLSec/mlflow.db` crea un directorio con nombre literal `PMT%20MLSec`. En este proyecto la URI se construye con `"sqlite:////" + str(PROJECT_ROOT / 'mlflow.db').lstrip("/")`.

**Trade-off Precision/Recall** → ver *Precision vs Recall — trade-off*.

**Training (entrenamiento)**
Proceso donde el modelo ajusta sus parámetros internos a partir de los ejemplos del training set. El modelo "ve" cada ejemplo, calcula el error entre su predicción y el label real, y ajusta los parámetros para reducir ese error. Al terminar, los parámetros quedan fijos — el modelo está listo para predecir sobre datos nuevos. **El modelo nunca debe ver el val o test set durante el training.**

**Hyperparameter (hiperparámetro)**
Parámetro de configuración del modelo que se fija **antes** del training — no se aprende de los datos. Ejemplos: `n_estimators=200` en Random Forest (cuántos árboles construir), `max_iter=1000` en Logistic Regression (cuántas iteraciones de optimización), `class_weight='balanced'` (cómo ponderar las clases). Se optimizan probando distintos valores y midiendo performance en el validation set.

**TCP window size (swin / dwin)**
Campo del header TCP que indica cuántos bytes puede recibir el receptor antes de que el emisor deba esperar un ACK. Rango: 0–255 en este dataset (en escala reducida). Un window size alto indica una conexión establecida y activa con flujo de datos — típico de tráfico legítimo. Los ataques de tipo scan o probe suelen tener `swin`/`dwin` = 0 porque nunca completan el handshake TCP. En UNSW-NB15: `swin` tiene correlación -0.334 con el label — mayor window = más probable tráfico normal.

**TCP sequence number (stcpb / dtcpb)**
Número de secuencia inicial del segmento TCP (ISN — Initial Sequence Number). Por diseño del protocolo, es un número pseudoaleatorio entre 0 y 2^32 (~4.29B). En UNSW-NB15: `stcpb` muestra correlación -0.255 con el label — inesperado para un valor que debería ser aleatorio. Puede reflejar un patrón en cómo el dataset fue generado. Se mantiene en el modelo inicial y se evalúa con feature importance post-training.

---

## X

**XGBoost (Extreme Gradient Boosting)**
Modelo de ensemble que construye árboles de decisión de forma **secuencial** — cada árbol aprende de los errores del anterior. A diferencia de Random Forest (árboles en paralelo independientes), XGBoost construye árboles que se corrigen mutuamente. Es uno de los modelos más usados en competencias de ML y datasets tabulares. Requiere `libomp` en macOS para funcionar. Hiperparámetro clave: `scale_pos_weight` para manejar desbalance de clases.

Usado en: **Modelo A (CSIC 2010)**. Resultado: ROC-AUC 0.933, Recall 0.964 ✅, Precision 0.594 ❌ — mayor Recall pero más FP que Random Forest.
Pendiente en: **Modelo B (UNSW-NB15)** — todavía no entrenado.

---

## U

**UNSW-NB15**
Dataset de tráfico de red generado por la University of New South Wales. Contiene 36 columnas (33 features + `attack_cat` + `label` + índice) con 9 categorías de ataque. Split predefinido: 175.341 train / 82.332 test. Usado para entrenar el Modelo B.

**Network flow features**
Métricas derivadas de una conexión de red capturada como flujo (flow). En lugar de inspeccionar el contenido de cada paquete, se analizan estadísticas del flujo completo: duración (`dur`), bytes enviados/recibidos (`sbytes`/`dbytes`), tasa de paquetes (`rate`), carga (`sload`/`dload`), jitter (`sjit`/`djit`), etc. Permiten detectar ataques sin necesidad de descifrar tráfico encriptado — solo se necesita la metadata de la conexión.
