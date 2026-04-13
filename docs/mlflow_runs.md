# Cómo leer un run de MLflow

Esta guía explica cómo interpretar la información de un run en el experimento `mlsec-model-a`. Está pensada para alguien con background técnico que necesita entender qué mira y qué decide a partir de los datos de MLflow.

---

## Contexto rápido

Cada vez que se entrena un modelo en este proyecto, MLflow registra un **run**: una snapshot completa de ese entrenamiento. Un run contiene:

- Los **parámetros** con los que se entrenó (algoritmo, versión de features, etc.)
- Las **métricas** de evaluación (ROC-AUC, Recall, Precision, etc.)
- Los **artefactos** generados (plots, modelo serializado)
- Metadata de sistema (cuándo se ejecutó, cuánto tardó, desde qué notebook)

El experimento `mlsec-model-a` agrupa todos los runs del Modelo A (CSIC 2010). Para verlos:

```bash
# Desde la raíz del proyecto
mlflow ui --backend-store-uri "sqlite:///mlflow.db"
# → http://localhost:5000 → clic en "mlsec-model-a"
```

---

## Anatomía de un run

### Panel izquierdo — "About this run"

| Campo | Qué es | Cómo usarlo |
|---|---|---|
| **Run ID** | UUID único del run (ej: `70c07c5d...`) | Para referenciar el run en código: `mlflow.load_model(f"runs:/{run_id}/model")` |
| **Created at** | Timestamp de ejecución | Para saber cuándo se hizo y ordenar cronológicamente |
| **Status** | `Finished` / `Failed` / `Running` | Un run `Failed` no tiene métricas confiables — ignorar |
| **Duration** | Tiempo de ejecución del run | Referencia para planificar re-entrenamientos |
| **Source** | Notebook o script que lo generó | Para reproducir exactamente: abrí ese notebook y re-ejecutá |
| **Experiment ID** | ID del experimento padre | Agrupa todos los runs del mismo modelo |

### Pestaña Overview — Métricas

Las 8 métricas loggeadas en cada run:

| Métrica | Qué mide | Criterio MVP | Cómo leerla |
|---|---|---|---|
| `roc_auc` | Capacidad del modelo de separar clases en **todos los thresholds**. 0.5 = aleatorio, 1.0 = perfecto | — | Indica el techo de calidad del modelo. Dos modelos con el mismo ROC-AUC tienen la misma capacidad teórica de separar clases, aunque el threshold óptimo varíe |
| `recall` | De todos los ataques reales, ¿cuántos detectó? | **≥ 0.95** | El número crítico de seguridad. 0.952 = detecta 95.2% de los ataques reales — el 4.8% restante pasa sin alarma |
| `precision` | De todas las alarmas que disparó, ¿cuántas eran ataques reales? | **≥ 0.85** | Mide el ruido de falsas alarmas. 0.713 = de cada 10 alarmas, 7.13 son ataques reales y 2.87 son tráfico normal mal clasificado |
| `f1` | Media armónica de Precision y Recall | — | Resumen en un número cuando no hay prioridad entre las dos métricas. En seguridad usamos Recall y Precision por separado porque sus criterios son distintos |
| `fp` | Cantidad absoluta de Falsos Positivos | — | Traduce Precision a algo concreto: 1444 FP = 1444 requests legítimos que el modelo marcaría como ataque por día (si el volumen es similar) |
| `fn` | Cantidad absoluta de Falsos Negativos | — | Traduce Recall a algo concreto: 179 FN = 179 ataques reales que pasarían sin detectar |
| `tp` | Verdaderos Positivos (ataques detectados correctamente) | — | Junto con FN: `Recall = TP / (TP + FN)` |
| `tn` | Verdaderos Negativos (tráfico normal clasificado correctamente) | — | Junto con FP: `Precision = TP / (TP + FP)` |

!!! tip "Cómo decidir si un run es bueno"
    Los criterios del MVP son **Recall ≥ 0.95** y **Precision ≥ 0.85**. Revisá esas dos métricas primero. Si un run no cumple Recall ≥ 0.95, está descartado — no importa cuánto mejore la Precision. Si cumple Recall pero no Precision, hay trabajo de features por hacer.

### Pestaña Overview — Parámetros

Los 10 parámetros loggeados documentan exactamente cómo se entrenó el run:

| Parámetro | Qué documenta |
|---|---|
| `model_type` | Algoritmo usado (ej: `LightGBM`) |
| `dataset` | Dataset de origen (`csic2010` o `unsw_nb15`) |
| `features_version` | Versión del preprocessing (`v1`, `v2`, `v3`...) — indica qué features tiene disponibles |
| `n_features` | Cantidad de features que recibió el modelo |
| `random_state` | Semilla de aleatoriedad — para reproducir exactamente el mismo split y modelo |
| `threshold` | Valor de decisión optimizado en validación — el score a partir del cual el modelo clasifica como "ataque" |
| `min_recall_threshold` | El Recall mínimo que se usó para calcular el threshold óptimo |
| `split` | División train/val/test usada |
| `class_weight` | Si se usó balanceo de clases |
| `scale_pos_weight` | Factor de escala para clases positivas (solo XGBoost/LightGBM) |

!!! info "Por qué importa el `threshold`"
    El modelo no predice "ataque" o "normal" directamente — predice una probabilidad entre 0 y 1. El threshold es el corte: si la probabilidad ≥ threshold → ataque. En v3 los thresholds son mucho menores que 0.5 (ej: 0.15 para RF) porque el dataset está desbalanceado. Si se usara 0.5, el Recall caería significativamente. El threshold loggeado en MLflow es el que da Recall ≥ 0.95 sobre validación.

### Pestaña Artifacts

Los artefactos son archivos generados durante el run. Para el experimento `mlsec-model-a`:

| Artefacto | Qué contiene | Para qué usarlo |
|---|---|---|
| `confusion_matrix.png` | Tabla TP/FP/TN/FN visualizada | Revisar la distribución de errores de un vistazo |
| `feature_importance.png` | Ranking de features por contribución al modelo | Decidir qué features explorar en la próxima iteración |
| `model/` | El modelo serializado (pickle + metadata MLflow) | Cargar el modelo para inferencia: `mlflow.sklearn.load_model(f"runs:/{run_id}/model")` |

Para ver los artefactos: clic en la pestaña **Artifacts** → navegar el árbol de archivos → clic en la imagen para preview en el browser.

### Logged models

Al final del panel Overview aparece la sección "Logged models". Muestra el modelo registrado en el run con su estado:

| Estado | Significado |
|---|---|
| `Ready` | El modelo está disponible para cargar e inferir |
| (sin estado) | El modelo se loggeó pero no se registró en el Model Registry |

La columna `roc_auc` en esta sección es el ROC-AUC del modelo en el momento del log — útil como referencia rápida sin abrir las métricas completas.

---

## Cómo comparar runs

La tabla del experimento `mlsec-model-a` muestra todos los runs juntos. Para tomar decisiones:

1. **Ir a http://localhost:5000** → clic en `mlsec-model-a`
2. **Seleccionar los runs a comparar** (checkbox a la izquierda)
3. **Clic en "Compare"** → vista paralela de métricas y parámetros

La columna `features_version` en los parámetros permite agrupar mentalmente los runs por iteración:

| features_version | Runs | Qué cambió |
|---|---|---|
| v3 | `model-a-lgbm-features-v3`, `model-a-rf-features-v3`, `model-a-xgboost-features-v3`, `model-a-logreg-features-v3` | + `content_pct_density` vs v2 |

!!! tip "Lectura rápida de la tabla"
    Ordená la tabla por `precision` (clic en la columna). Los runs con mejor Precision aparecen arriba. Si además tienen `recall` ≥ 0.95, son candidatos a analizar en detalle. Si no hay ninguno con ambas métricas cumplidas, el trabajo está en las features.

---

## Estado actual — runs en mlsec-model-a

| Run name | Algoritmo | features_version | ROC-AUC | Recall | Precision | FP | Estado |
|---|---|---|---|---|---|---|---|
| `model-a-lgbm-features-v3` | LightGBM | v3 | 0.955 | 0.952 ✅ | 0.713 ❌ | 1444 | Mejor Precision hasta ahora |
| `model-a-rf-features-v3` | Random Forest | v3 | 0.950 | 0.947 ❌ | 0.716 ❌ | 1416 | Recall < 0.95 con v3 |
| `model-a-xgboost-features-v3` | XGBoost | v3 | 0.948 | 0.958 ✅ | 0.649 ❌ | 1946 | Recall OK pero Precision baja |
| `model-a-logreg-features-v3` | Logistic Regression | v3 | 0.777 | 0.977 ✅ | 0.417 ❌ | 5138 | Descartado — no separa clases |

**Gap pendiente:** Precision 0.713 → 0.85 = 0.137 por cerrar. La próxima iteración (v4) trabaja sobre los 935 FP GET con análisis de estructura de URL.

---

## Flujo de decisión resumido

```
¿El run cumple Recall ≥ 0.95?
    ├── No → Bajar threshold o revisar el split. No pasar a producción.
    └── Sí → ¿Cumple Precision ≥ 0.85?
                ├── No → Analizar feature importance y FP. Planificar próxima iteración de features.
                └── Sí → Candidato a registrar en Model Registry.
                          Validar en test set. Registrar con mlflow.register_model().
```
