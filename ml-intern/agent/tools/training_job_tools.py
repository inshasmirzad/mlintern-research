"""Durable MongoDB training jobs and model ranking for local ML research."""

import asyncio
import re
import time
import uuid
from typing import Any

from agent.tools.local_ml_tools import SUPPORTED_TRAIN_MODELS, get_db

_index_lock = asyncio.Lock()
_index_ready = False


async def _ensure_job_index(db: Any) -> None:
    global _index_ready
    if _index_ready:
        return
    async with _index_lock:
        if not _index_ready:
            await db.training_jobs.create_index("run_id", unique=True)
            await db.models.create_index("run_id", unique=True, sparse=True)
            _index_ready = True


QUEUE_LOCAL_TRAINING_TOOL_SPEC = {
    "name": "queue_local_model_training",
    "description": (
        "Queue one distinct local model training job using a dataset already stored in MongoDB. "
        "Return a job ID immediately; a separately running training worker performs fitting "
        "and saves the model to GridFS. Use this for large or concurrent training workloads. "
        "If the user supplies a run_id, pass it exactly for later verification."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "dataset_id": {
                "type": "string",
                "description": "Existing MongoDB dataset ID.",
            },
            "model_type": {
                "type": "string",
                "description": "One supported classifier or regressor.",
            },
            "target_column": {"type": "string", "description": "Column to predict."},
            "run_id": {
                "type": "string",
                "description": "Unique client request ID for one saved model.",
            },
        },
        "required": ["dataset_id", "model_type", "target_column", "run_id"],
    },
}


async def queue_local_training_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    dataset_id = arguments.get("dataset_id")
    model_type = arguments.get("model_type")
    target_column = arguments.get("target_column")
    run_id = arguments.get("run_id")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (dataset_id, model_type, target_column, run_id)
    ):
        return "dataset_id, model_type, target_column and run_id are required.", False
    if model_type not in SUPPORTED_TRAIN_MODELS:
        return (
            f"Unsupported model_type. Choose from {sorted(SUPPORTED_TRAIN_MODELS)}.",
            False,
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        return (
            "run_id must contain 1–80 letters, numbers, underscores or hyphens.",
            False,
        )
    try:
        db = get_db()
        dataset = await db.datasets.find_one(
            {"dataset_id": dataset_id}, {"task_type": 1}
        )
        if dataset is None:
            return f"Dataset not found: {dataset_id}", False
        dataset_task = dataset.get("task_type")
        is_regression = (
            model_type.endswith("Regressor") or model_type == "LinearRegression"
        )
        if dataset_task == "regression" and not is_regression:
            return "This regression dataset needs a regressor model.", False
        if (
            dataset_task
            in {"classification", "binary_classification", "multiclass_classification"}
            and is_regression
        ):
            return "This classification dataset needs a classifier model.", False
        await _ensure_job_index(db)
        job_id = f"job_{uuid.uuid4().hex}"
        await db.training_jobs.update_one(
            {"run_id": run_id},
            {
                "$setOnInsert": {
                    "job_id": job_id,
                    "run_id": run_id,
                    "dataset_id": dataset_id,
                    "model_type": model_type,
                    "target_column": target_column,
                    "requested_by": getattr(session, "user_id", None),
                    "status": "queued",
                    "created_at": time.time(),
                }
            },
            upsert=True,
        )
        job = await db.training_jobs.find_one({"run_id": run_id})
        if any(
            job.get(key) != arguments[key]
            for key in ("dataset_id", "model_type", "target_column")
        ):
            return "run_id already belongs to a different training request.", False
        return (
            f"Training job queued. Job ID: {job['job_id']}; run_id: {run_id}; "
            f"status: {job['status']}. A training worker must be running."
        ), True
    except Exception as exc:
        return f"Could not queue training job: {type(exc).__name__}: {exc}", False


GET_LOCAL_TRAINING_JOB_TOOL_SPEC = {
    "name": "get_local_training_job",
    "description": "Check whether a queued local model training job completed, failed, or is still running.",
    "parameters": {
        "type": "object",
        "properties": {
            "run_id": {"type": "string", "description": "The request's run_id."}
        },
        "required": ["run_id"],
    },
}


async def get_local_training_job_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    job = await get_db().training_jobs.find_one({"run_id": arguments.get("run_id")})
    if job is None:
        return "Training job not found.", False
    return (
        f"Job ID: {job['job_id']}; status: {job['status']}; "
        f"model_id: {job.get('model_id', 'pending')}; "
        f"error: {job.get('error', 'none')}"
    ), True


GET_BEST_LOCAL_MODEL_TOOL_SPEC = {
    "name": "get_best_local_model",
    "description": (
        "Find the best saved model for one local dataset. Classification ranks by held-out "
        "accuracy; regression ranks by held-out R², not accuracy. Returns the model ID and metrics."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string", "description": "Existing dataset ID."}
        },
        "required": ["dataset_id"],
    },
}


async def get_best_local_model_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    dataset_id = arguments.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id:
        return "dataset_id is required.", False
    db = get_db()
    dataset = await db.datasets.find_one({"dataset_id": dataset_id})
    if dataset is None:
        return f"Dataset not found: {dataset_id}", False
    is_regression = dataset.get("task_type") == "regression"
    metric = "r2" if is_regression else "accuracy"
    models = await db.models.find(
        {"dataset_id": dataset_id, "status": "ready"}
    ).to_list(length=5000)
    ranked = []
    for model in models:
        metrics = model.get("metrics") or {}
        if not isinstance(metrics, dict):
            continue
        value = metrics.get(metric)
        if isinstance(value, (int, float)):
            ranked.append((float(value), model))
    if not ranked:
        return (
            f"No saved models with a held-out {metric} score for dataset {dataset_id}.",
            False,
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    top = ranked[:3]
    lines = [f"Best models for {dataset.get('name', dataset_id)} (ranked by {metric}):"]
    for score, model in top:
        lines.append(
            f"- {model.get('model_id')}: {model.get('name')} | {metric}={score:.4f} | "
            f"metrics={model.get('metrics')}"
        )
    lines.append(
        "These are saved-model scores; compare models on the same held-out split before claiming a winner."
    )
    return "\n".join(lines), True
