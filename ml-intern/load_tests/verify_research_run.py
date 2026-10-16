"""Audit a real LLM load run against MongoDB metadata and GridFS artifacts."""

import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import certifi
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 3)


def summary(values: list[float]) -> dict[str, float | None]:
    return {
        "mean": round(sum(values) / len(values), 4) if values else None,
        "min": round(min(values), 4) if values else None,
        "max": round(max(values), 4) if values else None,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--expected-users", type=int, default=1000)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", args.experiment_id):
        parser.error("Invalid experiment ID")
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    kwargs = {"serverSelectionTimeoutMS": 5000}
    if "+srv" in uri:
        kwargs["tlsCAFile"] = certifi.where()
    db = MongoClient(uri, **kwargs)[os.getenv("MONGO_DB_NAME", "ml_intern")]
    prefix = f"exp_{args.experiment_id}_"
    selector = {"run_id": {"$regex": "^" + re.escape(prefix)}}
    jobs = list(db.training_jobs.find(selector))
    models = list(db.models.find(selector))
    dataset_ids = {job.get("dataset_id") for job in jobs if job.get("dataset_id")}
    dataset_names = {
        dataset["dataset_id"]: dataset.get("name", dataset["dataset_id"])
        for dataset in db.datasets.find(
            {"dataset_id": {"$in": list(dataset_ids)}}, {"dataset_id": 1, "name": 1}
        )
    }
    job_by_run = {job["run_id"]: job for job in jobs}
    model_counts = Counter(model["run_id"] for model in models)
    valid = 0
    missing_artifacts = []
    wrong_model_id = []
    quality = defaultdict(lambda: defaultdict(list))
    artifact_sizes = defaultdict(list)
    for model in models:
        job = job_by_run.get(model["run_id"])
        if job is None or job.get("model_id") != model.get("model_id"):
            wrong_model_id.append(model["run_id"])
            continue
        try:
            artifact = db.fs.files.find_one(
                {"_id": ObjectId(model["gridfs_file_id"])}, {"length": 1}
            )
        except (KeyError, ValueError, TypeError):
            artifact = None
        if artifact is None:
            missing_artifacts.append(model["run_id"])
        elif job.get("status") == "completed" and model_counts[model["run_id"]] == 1:
            valid += 1
            model_type = model.get("model_type", "unknown")
            artifact_sizes[model_type].append(float(artifact["length"]))
            for metric in (
                "accuracy",
                "f1_macro",
                "balanced_accuracy",
                "r2",
                "rmse",
                "mae",
            ):
                value = (model.get("metrics") or {}).get(metric)
                if isinstance(value, (int, float)) and math.isfinite(value):
                    quality[model_type][metric].append(float(value))
    job_durations = [
        job["completed_at"] - job["created_at"]
        for job in jobs
        if job.get("status") == "completed" and "completed_at" in job
    ]
    queue_waits = [
        job["started_at"] - job["created_at"] for job in jobs if "started_at" in job
    ]
    fit_durations = [
        job["completed_at"] - job["started_at"]
        for job in jobs
        if job.get("status") == "completed"
        and "started_at" in job
        and "completed_at" in job
    ]
    statuses = Counter(job.get("status", "unknown") for job in jobs)
    passed = (
        valid == args.expected_users
        and len(jobs) == args.expected_users
        and len(models) == args.expected_users
        and statuses.get("completed", 0) == args.expected_users
    )
    report = {
        "experiment_id": args.experiment_id,
        "expected_users": args.expected_users,
        "queued_jobs": len(jobs),
        "missing_queued_jobs": max(0, args.expected_users - len(jobs)),
        "job_statuses": dict(statuses),
        "jobs_by_dataset": dict(
            Counter(
                dataset_names.get(job.get("dataset_id"), job.get("dataset_id", "unknown"))
                for job in jobs
            )
        ),
        "models_saved": len(models),
        "distinct_model_run_ids": len(model_counts),
        "verified_one_model_with_artifact": valid,
        "duplicate_model_run_ids": sorted(
            run for run, count in model_counts.items() if count != 1
        ),
        "missing_artifact_run_ids": missing_artifacts,
        "mismatched_job_model_run_ids": wrong_model_id,
        "models_by_type": dict(
            Counter(model.get("model_type", "unknown") for model in models)
        ),
        "queue_wait_seconds": summary(queue_waits),
        "fit_and_save_seconds": summary(fit_durations),
        "total_job_seconds": summary(job_durations),
        "quality_by_model_type": {
            model_type: {metric: summary(values) for metric, values in metrics.items()}
            for model_type, metrics in quality.items()
        },
        "artifact_bytes_by_model_type": {
            model_type: summary(values) for model_type, values in artifact_sizes.items()
        },
        "passed": passed,
    }
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
