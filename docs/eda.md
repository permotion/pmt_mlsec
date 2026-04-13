# EDA (Exploratory Data Analysis)

## Qué es y cuál es su rol

El EDA es la **investigación inicial de los datos** — se hace antes de construir cualquier pipeline. Su objetivo es entender la estructura del dataset, detectar problemas de calidad, y decidir qué features construir para el modelo.

```
[Ingesta]  →  [EDA]  →  [Preprocessing]  →  [Training]  →  [Experimentos]  →  [Registry]
                ↑               ↑                                  ↑
         exploración       implementación                    iteración sobre
         de datos          de decisiones                     modelo entrenado
         sin modelo        del EDA                           con resultados
```

**Outputs del EDA:**

1. **Conocimiento** — qué columnas usar, dónde viven los ataques, cómo tratar los nulos
2. **Decisiones de preprocessing** — qué normalizar, cómo encodear categóricas, estrategia para desbalance
3. **Features candidatas** — variables que el modelo va a recibir como input

Cuando el notebook madura, las transformaciones se convierten en scripts con `/refactor-notebook`.

### EDA vs Preprocessing vs Experimento

| | EDA | Preprocessing | Experimento |
|---|---|---|---|
| **Pregunta** | ¿Qué hay en los datos? | ¿Cómo transformo los datos? | ¿Por qué falla el modelo? |
| **Punto de partida** | Sin modelo | Decisiones del EDA | Modelo entrenado con resultados |
| **Output** | Conocimiento + decisiones | Features listas para training | Decisión de mejora |
| **Vive en** | `notebooks/eda/` | `src/mlsec/data/` | `notebooks/experiments/` |
| **Cambia con el tiempo** | No — es documentación estable | Solo si cambian las decisiones | Sí — itera con cada experimento |

---

## Estado

| Dataset | Notebook | EDA | Preprocessing |
|---|---|---|---|
| CSIC 2010 | `notebooks/eda/csic2010_eda.ipynb` | ✅ completo | ✅ `src/mlsec/data/preprocess_csic.py` |
| UNSW-NB15 | `notebooks/eda/unsw_nb15_eda.ipynb` | ✅ completo | ✅ `src/mlsec/data/preprocess_unsw.py` |

---

## EDA — CSIC 2010

**Modelo:** A — Web Attack Detection  
**Archivo:** `data/raw/csic2010/csic_database.csv`  
**Completado:** 2026-04-06 / 2026-04-10

---

### Estructura del dataset

- **Shape:** 61.065 filas × 17 columnas
- **Columnas originales:** `Unnamed: 0`, `Method`, `User-Agent`, `Pragma`, `Cache-Control`, `Accept`, `Accept-encoding`, `Accept-charset`, `language`, `host`, `cookie`, `content-type`, `connection`, `lenght`, `content`, `classification`, `URL`

---

### El label

!!! success "Label listo — sin transformación necesaria"
    `classification` ya está en `int64` con valores `[0, 1]`.  
    No necesita mapping. Columna renombrada a `label` para claridad.

- `Unnamed: 0` tiene el texto "Normal"/"Anomalous" — es redundante con el label, se descarta
- `0` = Normal, `1` = Attack

---

### Distribución de clases

| Clase | Registros | % |
|---|---|---|
| Normal (0) | 36.000 | 59% |
| Attack (1) | 25.065 | 41% |

Desbalance **leve** — no requiere SMOTE. Estrategia: `class_weight='balanced'` en el modelo.

---

### Distribución de métodos HTTP

| Method | Normal | Attack | % Attack |
|---|---|---|---|
| GET | 28.000 | 15.088 | 35% |
| POST | 8.000 | 9.580 | 54% |
| PUT | 0 | **397** | **100%** |

!!! danger "Hallazgo crítico — PUT = 100% ataques"
    Toda request PUT en el dataset es maliciosa.  
    `method_is_put` es la feature con mayor poder discriminativo — clasifica 397 ataques con precisión perfecta con un solo bit.

**Dónde viven los ataques según el método:**

- **GET** → el ataque está en la `URL` (query string — SQLi, XSS)
- **POST** → el ataque está en `content` (body del request)
- **PUT** → el método en sí es el indicador de ataque

---

### Nulos

| Columna | Nulos | % | Causa | Estrategia |
|---|---|---|---|---|
| `content` | 43.088 | 70.56% | Requests GET no tienen body | No imputar — rellenar con `""` o `0` |
| `lenght` | 43.088 | 70.56% | Requests GET no tienen body | `content_length = 0` para GETs |
| `content-type` | 43.088 | 70.56% | Requests GET no tienen body | Descartar — constante entre no-nulos |
| `Accept` | 397 | 0.65% | Desconocida | Descartar — columna constante |

Los 43.088 nulos corresponden exactamente a los requests GET. **No es un error de calidad de datos** — es el diseño del protocolo HTTP (los GETs no tienen body).

---

### Columnas descartadas

| Columna | Razón |
|---|---|
| `Unnamed: 0` | Redundante con label |
| `User-Agent` | Constante — 1 único valor en todo el dataset |
| `Pragma` | Constante — 1 único valor |
| `Cache-Control` | Constante — 1 único valor |
| `Accept` | Constante — 1 único valor |
| `Accept-encoding` | Constante — 1 único valor |
| `Accept-charset` | Constante — 1 único valor |
| `language` | Constante — 1 único valor |
| `content-type` | Constante entre no-nulos |
| `host` | 2 valores, sin señal útil |
| `connection` | 2 valores, sin señal útil |

**Total: 11 columnas eliminadas** de 17 originales. Quedan 6 con información útil: `Method`, `cookie`, `lenght`, `content`, `URL`, `label`.

---

### Análisis de URL length

Las distribuciones de longitud de URL se solapan entre normal y ataque — ambas concentradas en 50-100 chars. Los ataques tienen cola más larga (~400 chars vs ~330 en normales).

**Conclusión:** `url_length` sola no discrimina bien, pero aporta como feature **combinada** con los indicadores de texto.

---

### Correlación de indicadores en URL con label

!!! warning "Hallazgo crítico — URL encoding"
    Los caracteres especiales `'`, `"`, `<`, `>`, `;` **nunca aparecen crudos** en las URLs.  
    Los atacantes siempre los codifican (`%27`, `%3C`, etc.) para evadir filtros.  
    El feature engineering debe buscar las versiones **percent-encoded**, no los literales.

| Indicador | Significado | Correlación con label |
|---|---|---|
| `url_has_pct27` | `%27` = `'` URL-encoded | **0.183** |
| `url_has_dashdash` | `--` = comentario SQL | **0.148** |
| `url_has_script` | keyword XSS | **0.137** |
| `url_has_pct3c` | `%3C` = `<` URL-encoded | **0.124** |
| `url_has_select` | keyword SQL SELECT | 0.050 |
| `url_has_union` | keyword SQL UNION | ~0.000 — descartar |
| `'`, `"`, `<`, `>`, `;` crudos | Caracteres literales | NaN — nunca aparecen |

---

### Análisis del content (body POST)

| Métrica | Normal | Attack |
|---|---|---|
| Requests POST totales | 8.000 | 9.580 |
| Content length — media | 91.6 chars | 123.2 chars |
| Content length — mediana | 47.5 chars | 72.0 chars |
| Content length — P75 | 110.5 chars | **243.0 chars** |
| Content length — máximo | 307 chars | **836 chars** |

Ataques POST tienen body **35% más largo en promedio** con cola mucho más pesada. `content_length` es una feature discriminativa para requests POST.

---

### Decisiones de preprocessing

| Decisión | Detalle |
|---|---|
| Desbalance | `class_weight='balanced'` — no SMOTE |
| Nulos en content/lenght | `content_length = 0` para GETs — no NaN |
| Encoding de Method | One-hot: `method_is_get`, `method_is_post`, `method_is_put` |
| Indicadores de texto | Percent-encoded (`%27`, `%3C`) — no chars literales |
| Normalización | Solo features continuas: `url_length`, `content_length` |
| Features binarias | Sin normalizar — ya están en 0/1 |

---

### Features finales — Modelo A

| Feature | Fuente | Tipo | Importancia |
|---|---|---|---|
| `method_is_put` | `Method` | Binaria | ⭐⭐⭐ — 100% ataques |
| `method_is_post` | `Method` | Binaria | ⭐⭐ — tasa 54% ataque |
| `method_is_get` | `Method` | Binaria | ⭐ — referencia |
| `url_has_pct27` | `URL` | Binaria | ⭐⭐ — corr 0.183 |
| `url_has_dashdash` | `URL` | Binaria | ⭐⭐ — corr 0.148 |
| `url_has_script` | `URL` | Binaria | ⭐⭐ — corr 0.137 |
| `url_has_pct3c` | `URL` | Binaria | ⭐⭐ — corr 0.124 |
| `url_has_select` | `URL` | Binaria | ⭐ — corr 0.050 |
| `url_length` | `URL` | Numérica | ⭐ — útil combinada |
| `content_length` | `content` | Numérica | ⭐⭐ — ataques POST más largos |
| `content_has_*` | `content` | Binaria | pendiente — mismos indicadores en body |

---

## EDA — UNSW-NB15

**Modelo:** B — Network Attack Detection  
**Archivos:** `data/raw/unsw_nb15/UNSW_NB15_training-set.parquet`, `UNSW_NB15_testing-set.parquet`  
**Estado:** completado ✅

### Estructura del dataset

- **Shape:** Train 175.341 × 36 / Test 82.332 × 36
- **Split:** ya viene predefinido en el parquet — no modificar
- **36 columnas:** 33 features + `attack_cat` + `label` + 1 implícita de índice

### Dtypes — observaciones

| Tipo | Columnas | Nota |
|---|---|---|
| `float32` | `dur`, `rate`, `sload`, `dload`, `sinpkt`, `djit`, etc. | Optimizado — no float64 |
| `int8 / int16 / int32` | mayoría de features enteras | Optimizado en memoria |
| `category` | `proto`, `service`, `state`, `attack_cat` | Ya listas, sin conversión manual |
| `int8` | `label` | Target — valores 0/1 ✅ |

El parquet **ya viene con dtypes optimizados** — señal de que fue procesado con cuidado. Las categóricas tienen dtype `category` nativo de pandas.

**`attack_cat`:** columna categórica con los 9 tipos de ataque. Solo se usa para análisis — **no va como input al modelo** (usamos label binario).

### El label

- `label` es `int8` con valores `[0, 1]` ✅ — listo, sin transformación
- `0` = Benign, `1` = Malicious — consistente con el resto del proyecto

### Distribución de clases

| Split | Benign (0) | Malicious (1) | % Malicious |
|---|---|---|---|
| Train | 56.000 | 119.341 | **68.1%** |
| Test | 37.000 | 45.332 | **55.1%** |

!!! warning "Desbalance inverso — más ataques que tráfico normal"
    A diferencia de CSIC 2010 (59% normal), acá los ataques son mayoría en train (68%).
    Además el ratio es **distinto entre train y test** — train tiene más ataques proporcionalmente.
    Esto es inusual pero está documentado en el paper original de UNSW-NB15.

**Estrategia de desbalance:** a definir en el EDA — evaluar `class_weight='balanced'` vs SMOTE.
Con 68/32 el desbalance es moderado-alto — SMOTE puede ser necesario.

### Categorías de ataque (attack_cat)

Solo para análisis — no va como input al modelo. Usamos label binario (0/1).

| Categoría | Registros | % de ataques | Descripción |
|---|---|---|---|
| Generic | 40.000 | 33.5% | Ataques genéricos no clasificados |
| Exploits | 33.393 | 28.0% | Explotación de vulnerabilidades conocidas |
| Fuzzers | 18.184 | 15.2% | Input malformado para encontrar bugs |
| DoS | 12.264 | 10.3% | Denegación de servicio |
| Reconnaissance | 10.491 | 8.8% | Escaneo y reconocimiento de red |
| Analysis | 2.000 | 1.7% | Análisis de tráfico / sniffing |
| Backdoor | 1.746 | 1.5% | Acceso remoto no autorizado |
| Shellcode | 1.133 | 0.9% | Ejecución de código malicioso |
| Worms | 130 | 0.1% | Auto-propagación de malware |

!!! warning "Worms severamente sub-representado"
    130 registros vs 40.000 de Generic — ratio 1:307. Aunque usamos label binario, el modelo va a tener muy pocos ejemplos de patrones de Worms. Si el recall en esta categoría es bajo, es esperado.

**Top 3 categorías concentran el 76.7% de los ataques:** Generic + Exploits + Fuzzers.

### Nulos

!!! success "Sin nulos — las 36 columnas están completas"
    No hay estrategia de imputación necesaria para UNSW-NB15.

**Nota:** el valor `-` en la columna `service` no es un nulo técnico — es una categoría propia que significa "sin servicio identificado". Se analizará en la sección de features categóricas.

### Features categóricas

#### proto — 133 valores únicos

!!! warning "Alta cardinalidad — requiere reducción"
    One-hot encoding directo generaría 133 columnas. Estrategia: mantener top-10 más frecuentes + categoría `other` para el resto.

| Valor | Registros | % | Descripción |
|---|---|---|---|
| tcp | 79.946 | 45.6% | Transmission Control Protocol |
| udp | 63.283 | 36.1% | User Datagram Protocol |
| unas | 12.084 | 6.9% | Unassigned protocol |
| arp | 2.859 | 1.6% | Address Resolution Protocol |
| ospf | 2.595 | 1.5% | Routing protocol |
| otros 128 | ~14.574 | 8.3% | → agrupar en `other` |

TCP + UDP + unas = **88.6% del tráfico**. El resto se agrupa.

#### service — 13 valores únicos

One-hot encoding directo. `-` **no es un nulo** — es la categoría "sin servicio identificado" y es la más frecuente (53.6%).

| Valor | Registros | % |
|---|---|---|
| `-` | 94.168 | 53.6% |
| dns | 47.294 | 27.0% |
| http | 18.724 | 10.7% |
| smtp | 5.058 | 2.9% |
| ftp-data | 3.995 | 2.3% |
| otros 8 | ~6.102 | 3.5% |

#### state — 9 valores únicos

One-hot encoding directo. INT + FIN + CON = 99% del tráfico.

| Valor | Registros | % | Descripción |
|---|---|---|---|
| INT | 82.275 | 46.9% | Intermediate — conexión en curso |
| FIN | 77.825 | 44.4% | Connection finished normalmente |
| CON | 13.152 | 7.5% | UDP/ICMP — conexión establecida |
| RST | 83 | 0.05% | Reset — conexión terminada abruptamente |
| otros 5 | 16 | ~0% | Casos extremadamente raros |

#### Estrategia de encoding por columna

| Columna | Cardinalidad | Estrategia |
|---|---|---|
| `proto` | 133 | Top-10 + categoría `other` → one-hot |
| `service` | 13 | One-hot directo (13 columnas) |
| `state` | 9 | One-hot directo (9 columnas) |

### Estadísticas descriptivas — features numéricas

#### Outliers extremos

Varias features tienen media >> mediana — distribuciones con cola muy pesada. StandardScaler no es adecuado para estas features.

| Feature | Mediana | Media | Máximo | Observación |
|---|---|---|---|---|
| `sbytes` | 430 | 8.844 | 12.965.230 | Cola extrema — bytes enviados |
| `dbytes` | 164 | 14.928 | 14.655.550 | Cola extrema — bytes recibidos |
| `sload` | 879.674 | 73.454.030 | 5.988.000.000 | Cola extrema — source load |
| `dload` | 1.447 | 671.205 | 22.422.730 | Cola extrema — dest load |
| `response_body_len` | 0 | 2.144 | 6.558.056 | P75=0, muy sparse |
| `sjit` | 0 | 4.976 | 1.460.480 | Jitter extremo |
| `rate` | 3.225 | 95.406 | 1.000.000 | Max=1M exacto — posible cap artificial |

**Estrategia de normalización:** `RobustScaler` (usa mediana e IQR, resistente a outliers) o log-transform + StandardScaler para las features con cola más pesada.

#### Features sparse (median=0, P75=0)

Estas features están en cero para la mayoría del tráfico — solo activan en casos específicos:

`trans_depth`, `response_body_len`, `is_ftp_login`, `ct_ftp_cmd`, `ct_flw_http_mthd`, `tcprtt`, `synack`, `ackdat`, `sloss`, `dloss`, `sjit`, `djit`

Son útiles igual — cuando activan, pueden ser muy discriminativas.

#### Distribuciones por clase — histogramas de features de flujo

| Feature | Patrón observado | Poder discriminativo |
|---|---|---|
| `rate` | Ataques distribuidos uniformemente hasta 1M. Normal concentrado cerca de 0 | ⭐⭐⭐ Alto |
| `sload` | Ataques con distribución más multimodal. Normal más concentrado | ⭐⭐ Medio |
| `sbytes` | Ambas clases concentradas cerca de 0, ataques con cola más pesada | ⭐ Bajo-medio |
| `dur` | Ambas concentradas cerca de 0. Ataques tienden a ser más cortos | ⭐ Bajo-medio |
| `dbytes` | **Normal tiene MÁS bytes recibidos que ataques** | ⭐⭐ Medio |
| `dload` | **Normal domina completamente** — tráfico legítimo descarga más datos | ⭐⭐ Medio |

!!! info "Patrón inverso en dbytes y dload"
    El tráfico normal tiene más bytes recibidos que los ataques. Tiene sentido: el tráfico legítimo descarga datos (HTTP responses, DNS replies). Muchos ataques son scans o probes que no reciben respuesta — envían paquetes pero no reciben nada back.

**Estrategia de normalización confirmada:** `RobustScaler` para todas las features de flujo — distribuciones extremadamente skewed, StandardScaler quedaría inutilizado por los outliers.

#### Anomalías a investigar

| Feature | Problema | Decisión |
|---|---|---|
| `is_ftp_login` | Max=4 — debería ser binaria 0/1 | Investigar — posible error o conteo |
| `stcpb` / `dtcpb` | Números de secuencia TCP hasta 4.29B — aleatorios por diseño | Candidatas a descartar |
| `rate` | Max=1.000.000 exacto | Posible cap artificial — verificar |
| `swin` / `dwin` | Bounded 0-255 (TCP window size) | MinMaxScaler o sin normalizar |

### Correlación de features con label

#### Top features — correlación positiva (más valor → más probable ataque)

| Feature | Correlación | Interpretación |
|---|---|---|
| `ct_dst_sport_ltm` | **0.357** | Conteo de conexiones recientes al mismo destino/puerto — ataques generan muchas conexiones |
| `rate` | **0.338** | Tasa de paquetes por segundo — ataques tienen rate más alto y uniforme |
| `ct_src_dport_ltm` | **0.306** | Conteo de conexiones recientes del mismo source — scanning pattern |
| `sload` | 0.183 | Carga de la fuente — ataques envían más datos |
| `ackdat` | 0.097 | Tiempo entre SYN-ACK y ACK — patrón TCP anómalo |
| `tcprtt` | 0.082 | Round-trip time TCP |
| `synack` | 0.058 | Tiempo de SYN-ACK |

#### Top features — correlación negativa (más valor → más probable tráfico normal)

| Feature | Correlación | Interpretación |
|---|---|---|
| `dload` | **-0.394** | Tráfico normal descarga más datos — ataques son probes sin respuesta |
| `dmean` | **-0.342** | Tamaño medio de paquetes recibidos — mayor en tráfico legítimo |
| `swin` | **-0.334** | TCP window size source — mayor en conexiones legítimas establecidas |
| `dwin` | **-0.320** | TCP window size dest — mayor en conexiones legítimas |
| `stcpb` | -0.255 | Número de secuencia TCP — correlación inesperada, **no descartar todavía** |

#### Features con correlación ~0 → candidatas a descartar

`sloss` (-0.001), `sjit` (-0.007), `smean` (-0.011), `ct_ftp_cmd` (-0.011)

> **Importante:** correlación lineal baja no significa que la feature sea inútil para modelos no-lineales como Random Forest. Confirmar importancia después del training.

#### Decisión sobre stcpb / dtcpb

`stcpb` muestra correlación -0.255 — inesperado para un número de secuencia TCP que debería ser aleatorio. Puede haber un patrón en cómo el dataset fue generado. **Mantener en el modelo inicial** y evaluar feature importance post-training.

### Correlación entre features (heatmap de redundancias)

Análisis de correlación entre las top 15 features por correlación con el label. Objetivo: identificar pares redundantes para simplificar el modelo.

#### Pares altamente correlacionados (> 0.9) — candidatos a eliminación

| Par | Correlación | Decisión |
|---|---|---|
| `swin` / `dwin` | **0.99** | Descartar `dwin` — casi idénticas (TCP window size source/dest) |
| `dpkts` / `dloss` | **0.98** | Descartar `dloss` — derivada de `dpkts` |
| `is_sm_ips_ports` / `sinpkt` | **0.94** | Descartar `is_sm_ips_ports` — `sinpkt` tiene mayor correlación con label |
| `ct_dst_sport_ltm` / `ct_src_dport_ltm` | **0.91** | Mantener ambas — aunque correlacionadas, capturan perspectivas distintas (destino vs source) |

#### Pares moderadamente correlacionados (0.6–0.9) — mantener ambas

| Par | Correlación | Nota |
|---|---|---|
| `stcpb` / `dtcpb` | **0.65** | Mantener — correlación moderada, perspectivas distintas |
| `rate` / `ct_dst_sport_ltm` | ~0.5 | Mantener — rate es tasa de paquetes, ct_ es conteo de conexiones |

!!! info "Por qué eliminar features correlacionadas"
    Dos features con correlación 0.99 aportan casi la misma información al modelo. Mantenerlas no mejora la predicción pero aumenta el ruido y la dimensionalidad. En Random Forest esto tiene poco impacto práctico, pero es buena práctica reducir redundancias antes de entrenar.

#### Features descartadas por redundancia

| Feature | Razón | Reemplazada por |
|---|---|---|
| `dwin` | 0.99 de correlación con `swin` | `swin` |
| `dloss` | 0.98 de correlación con `dpkts` | `dpkts` |
| `is_sm_ips_ports` | 0.94 con `sinpkt`, menor correlación con label | `sinpkt` |

### Features constantes o de baja varianza

Features numéricas con pocos valores únicos (< 10) — candidatas a descartar o tratar especialmente:

| Feature | Valores únicos | Tipo real | Decisión |
|---|---|---|---|
| `is_sm_ips_ports` | 2 | Binaria | **Descartar** — ya identificada como redundante con `sinpkt` (correlación 0.94) |
| `dwin` | 7 | Casi binaria | **Descartar** — ya identificada como redundante con `swin` (correlación 0.99) |
| `is_ftp_login` | 4 | Debería ser binaria | **Mantener con precaución** — max=4 es una anomalía (debería ser 0/1). Puede ser conteo en lugar de flag binario. Validar con feature importance post-training |
| `ct_ftp_cmd` | 4 | Conteo | **Mantener** — sparse pero potencialmente discriminativa para conexiones FTP. Correlación ~0 en el dataset global no implica que sea inútil en Random Forest |

!!! info "Baja varianza ≠ inútil"
    Una feature binaria o con pocos valores únicos puede ser muy discriminativa si los pocos valores se distribuyen de forma diferente entre clases. `is_sm_ips_ports` y `dwin` se descartan por **redundancia**, no solo por baja varianza.

### Decisiones finales — UNSW-NB15

| Decisión | Detalle |
|---|---|
| **Normalización** | `RobustScaler` para todas las features numéricas continuas |
| **Encoding** | Top-10+other para `proto`, one-hot directo para `service` y `state` |
| **Desbalance** | Evaluar `class_weight='balanced'` primero — desbalance 68/32 |
| **Nulos** | Sin imputación necesaria — dataset completo |
| **Features descartadas** | `dwin`, `dloss`, `is_sm_ips_ports` (redundantes) |
| **Features a monitorear** | `stcpb`, `dtcpb` — correlación inesperada, validar con feature importance |
| **attack_cat** | Solo para análisis — no va como input al modelo |

### Plan de análisis

| Análisis | Herramienta | Output esperado |
|---|---|---|
| Distribución de `attack_cat` | `value_counts()` + barplot | Entender los 9 tipos de ataque |
| Distribución de clases | `label.value_counts()` | Confirmar desbalance 68/32 |
| Correlación entre features numéricas | heatmap | Features redundantes a eliminar |
| Outliers en features de flujo | boxplot + IQR | Estrategia de normalización |
| Valores únicos en categóricas | `nunique()` | Estrategia de encoding |
| Nulos / valores `-` en `service` | `isnull()` + `value_counts()` | Imputación o categoría propia |

---

## Checklist de completion

- [x] Label confirmado en 0/1 — CSIC 2010 ✅
- [x] Features CSIC 2010 definidas ✅
- [x] Estrategia de nulos CSIC 2010 ✅
- [x] Estrategia de normalización CSIC 2010 ✅
- [x] Estrategia de desbalance CSIC 2010 — `class_weight='balanced'` ✅
- [x] Label confirmado en 0/1 — UNSW-NB15 ✅
- [x] Features UNSW-NB15 analizadas — correlación con label + redundancias ✅
- [x] Estrategia de nulos UNSW-NB15 — sin nulos, no requiere imputación ✅
- [x] Estrategia de normalización UNSW-NB15 — RobustScaler ✅
- [x] Estrategia de desbalance UNSW-NB15 — evaluar class_weight='balanced' ✅
- [x] Features redundantes identificadas — dwin, dloss, is_sm_ips_ports descartadas ✅
- [x] `docs/models.md` actualizado con todas las decisiones UNSW-NB15 ✅
