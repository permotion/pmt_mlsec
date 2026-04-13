# MLflow

## Instalación

MLflow ya está instalado en el entorno virtual del proyecto (versión 3.11.1). Figura en `requirements.txt` como dependencia.

```bash
# Instalar todas las dependencias del proyecto (incluye MLflow)
pip install -r requirements.txt

# O instalar solo MLflow
pip install mlflow
```

Primera integración en código: `notebooks/experiments/csic2010_feature_analysis_v3.ipynb`.

## Levantar el servidor

```bash
# Desde la raíz del proyecto
mlflow ui --backend-store-uri "sqlite:///mlflow.db"
# → http://localhost:5000
```

El backend store es `mlflow.db` (SQLite) en la raíz del proyecto. El file-based store (`mlruns/`) está deprecado en MLflow 3.x.

**Nota:** Los runs del v3 fueron creados antes de fijar el tracking URI y quedaron en `notebooks/experiments/mlruns/`. A partir del v4 todos los runs van al `mlflow.db` de la raíz.

---

## Convenciones de naming

### Experiments (agrupan runs del mismo modelo)

```
mlsec-model-a          ← todos los runs del Modelo A
mlsec-model-b          ← todos los runs del Modelo B
```

### Runs (cada entrenamiento individual)

```
{modelo}-{algoritmo}-{descripcion}

Ejemplos:
  model-a-logreg-baseline
  model-a-rf-feature-selection-v2
  model-b-xgboost-smote
```

---

## Qué loggear en cada run

### Parámetros (`mlflow.log_param`)
```python
mlflow.log_param("model_type", "RandomForest")
mlflow.log_param("n_estimators", 100)
mlflow.log_param("random_state", 42)
mlflow.log_param("dataset", "unsw_nb15")
mlflow.log_param("threshold", 0.45)
mlflow.log_param("class_weight", "balanced")
```

### Métricas (`mlflow.log_metric`)
```python
mlflow.log_metric("precision", precision)
mlflow.log_metric("recall", recall)
mlflow.log_metric("f1", f1)
mlflow.log_metric("roc_auc", roc_auc)
```

### Artefactos (`mlflow.log_artifact`)
```python
mlflow.log_artifact("confusion_matrix.png")
mlflow.log_artifact("feature_importance.png")
mlflow.sklearn.log_model(model, "model")
```

---

## Ejemplo de run completo

```python
import mlflow
import mlflow.sklearn

mlflow.set_experiment("mlsec-model-b")

with mlflow.start_run(run_name="model-b-rf-baseline"):
    # Parámetros
    mlflow.log_param("model_type", "RandomForest")
    mlflow.log_param("n_estimators", 100)
    mlflow.log_param("dataset", "unsw_nb15")
    mlflow.log_param("threshold", 0.5)

    # Training
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    # Métricas
    mlflow.log_metric("precision", precision_score(y_val, y_pred))
    mlflow.log_metric("recall", recall_score(y_val, y_pred))
    mlflow.log_metric("f1", f1_score(y_val, y_pred))
    mlflow.log_metric("roc_auc", roc_auc_score(y_val, y_proba))

    # Modelo
    mlflow.sklearn.log_model(model, "model")
```

---

## Model Registry

Cuando un run supera los criterios de éxito del MVP, se registra:

```python
mlflow.register_model(
    f"runs:/{run_id}/model",
    "mlsec-model-b-production"
)
```

---

## `.gitignore`

```
mlruns/
```

Los runs de MLflow son locales. No versionar.
