-- Crea la base de datos para MLflow
-- La base de datos de Airflow es creada automáticamente por POSTGRES_DB
CREATE DATABASE mlflow;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO airflow;
