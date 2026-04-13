"""
Migración de runs: MLflow SQLite (local) → MLflow Postgres (Docker)

Qué migra:  params, métricas, tags, run name, status, timestamps
Qué NO migra: artefactos (modelos) — quedan como backup en mlruns/ local

Requisito: docker compose up mlflow (postgres + mlflow corriendo)

Uso:
    python docker/migrate_mlflow.py
    python docker/migrate_mlflow.py --src sqlite:///mlflow.db --dst http://localhost:5081
"""

import argparse
import time
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

ROOT = Path(__file__).resolve().parents[1]

SRC_DEFAULT = f"sqlite:///{ROOT / 'mlflow.db'}"
DST_DEFAULT = "http://localhost:5081"

SKIP_TAG_PREFIXES = ("mlflow.source", "mlflow.user", "mlflow.log-model")


def wait_for_server(uri: str, retries: int = 10, delay: float = 2.0):
    import urllib.request
    import urllib.error
    health_url = f"{uri}/health"
    for i in range(retries):
        try:
            urllib.request.urlopen(health_url, timeout=3)
            print(f"MLflow server listo en {uri}")
            return
        except Exception:
            print(f"Esperando servidor MLflow ({i+1}/{retries})...")
            time.sleep(delay)
    raise RuntimeError(f"No se pudo conectar al servidor MLflow en {uri}")


def migrate(src_uri: str, dst_uri: str):
    wait_for_server(dst_uri)

    src = MlflowClient(tracking_uri=src_uri)
    dst = MlflowClient(tracking_uri=dst_uri)

    experiments = src.search_experiments(view_type=mlflow.entities.ViewType.ALL)
    print(f"\nExperimentos encontrados en origen: {len(experiments)}")

    total_runs = 0
    skipped = 0

    for exp in experiments:
        if exp.name == "Default":
            dst_exp_id = "0"
        else:
            existing = dst.get_experiment_by_name(exp.name)
            if existing:
                dst_exp_id = existing.experiment_id
                print(f"  Experimento '{exp.name}' ya existe en destino (id={dst_exp_id})")
            else:
                dst_exp_id = dst.create_experiment(exp.name)
                print(f"  Experimento '{exp.name}' creado en destino (id={dst_exp_id})")

        runs = src.search_runs(
            experiment_ids=[exp.experiment_id],
            run_view_type=mlflow.entities.ViewType.ALL,
        )
        print(f"  Runs a migrar: {len(runs)}")

        for run in runs:
            run_name = run.info.run_name or "migrated-run"

            # Chequear si ya existe un run con el mismo nombre y métricas
            existing_runs = dst.search_runs(
                experiment_ids=[dst_exp_id],
                filter_string=f"tags.`migrated_from_run_id` = '{run.info.run_id}'",
            )
            if existing_runs:
                print(f"    Run '{run_name}' ya migrado, saltando.")
                skipped += 1
                continue

            # Crear el run en destino
            dst_run = dst.create_run(
                experiment_id=dst_exp_id,
                run_name=run_name,
                start_time=run.info.start_time,
            )
            dst_run_id = dst_run.info.run_id

            # Params
            for k, v in run.data.params.items():
                dst.log_param(dst_run_id, k, v)

            # Métricas (valor final de cada métrica)
            for k, v in run.data.metrics.items():
                dst.log_metric(dst_run_id, k, v)

            # Tags (filtra tags internas de MLflow)
            tags = {
                k: v for k, v in run.data.tags.items()
                if not any(k.startswith(p) for p in SKIP_TAG_PREFIXES)
            }
            tags["migrated_from_run_id"] = run.info.run_id
            tags["migrated_from_uri"] = src_uri
            for k, v in tags.items():
                dst.set_tag(dst_run_id, k, v)

            # Cerrar el run con el mismo status
            status = run.info.status  # FINISHED, FAILED, RUNNING, etc.
            if status == "FINISHED":
                dst.set_terminated(dst_run_id, "FINISHED", end_time=run.info.end_time)
            elif status == "FAILED":
                dst.set_terminated(dst_run_id, "FAILED", end_time=run.info.end_time)
            else:
                dst.set_terminated(dst_run_id, "FINISHED")

            print(f"    ✓ Run '{run_name}' migrado (src={run.info.run_id[:8]}… → dst={dst_run_id[:8]}…)")
            total_runs += 1

    print(f"\nMigración completada: {total_runs} runs migrados, {skipped} ya existían.")
    print(f"UI disponible en: {dst_uri}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migra runs de MLflow SQLite → Postgres")
    parser.add_argument("--src", default=SRC_DEFAULT, help="URI de origen (SQLite)")
    parser.add_argument("--dst", default=DST_DEFAULT, help="URI de destino (servidor HTTP)")
    args = parser.parse_args()

    print(f"Origen:  {args.src}")
    print(f"Destino: {args.dst}")
    migrate(args.src, args.dst)
