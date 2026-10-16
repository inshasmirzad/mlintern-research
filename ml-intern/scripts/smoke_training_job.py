"""Exercise the real MongoDB queue, multiclass XGBoost fit, and GridFS save."""

import asyncio
import io
import json
import os
import pickle
import sys
import uuid
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from gridfs import AsyncGridFSBucket
from sklearn.datasets import load_iris

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from agent.tools.local_ml_tools import train_local_model_handler
from agent.tools.training_job_tools import (
    get_best_local_model_handler,
    queue_local_training_handler,
)
from backend.database import get_db
from scripts.training_worker import process_one


async def main() -> None:
    db = get_db()
    await db.command("ping")
    dataset = await db.datasets.find_one(
        {"name": "Iris Species"}, sort=[("created_at", -1)]
    )
    if dataset is None:
        raise RuntimeError("Iris Species is not seeded in MongoDB")
    run_id = f"smoke_{uuid.uuid4().hex}"
    request = {
        "run_id": run_id,
        "dataset_id": dataset["dataset_id"],
        "model_type": "XGBClassifier",
        "target_column": "target",
    }
    _, queued = await queue_local_training_handler(request)
    if not queued:
        raise RuntimeError("Queue rejected the smoke training request")
    _, queued_again = await queue_local_training_handler(request)
    if (
        not queued_again
        or await db.training_jobs.count_documents({"run_id": run_id}) != 1
    ):
        raise RuntimeError("Queue was not idempotent for the same run_id")
    if not await process_one(f"smoke:{os.getpid()}", run_id):
        raise RuntimeError("Worker could not claim the smoke job")
    job = await db.training_jobs.find_one({"run_id": run_id})
    model = await db.models.find_one({"run_id": run_id, "status": "ready"})
    if job["status"] != "completed" or model is None:
        raise RuntimeError(
            f"Smoke job did not complete: {job.get('error', job['status'])}"
        )
    if await db.models.count_documents({"run_id": run_id}) != 1:
        raise RuntimeError("Smoke request saved more than one model")
    _, cached = await train_local_model_handler(request | {"force_retrain": True})
    if not cached or await db.models.count_documents({"run_id": run_id}) != 1:
        raise RuntimeError("Retry did not reuse the saved run_id")
    artifact = await db.fs.files.find_one({"_id": ObjectId(model["gridfs_file_id"])})
    if artifact is None or model["metrics"].get("classes") != 3:
        raise RuntimeError("Multiclass artifact or metrics are missing")
    model_bytes = io.BytesIO()
    await AsyncGridFSBucket(db).download_to_stream(
        ObjectId(model["gridfs_file_id"]), model_bytes
    )
    restored = pickle.loads(model_bytes.getvalue())
    sample = load_iris(as_frame=True).frame.drop(columns=["target"]).iloc[:3]
    if len(restored.predict(sample)) != 3:
        raise RuntimeError("Saved model could not be restored for prediction")
    _, ranking_ok = await get_best_local_model_handler(
        {"dataset_id": dataset["dataset_id"]}
    )
    if not ranking_ok:
        raise RuntimeError("Best-model lookup failed")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "job_status": job["status"],
                "model_id": model["model_id"],
                "classes": model["metrics"]["classes"],
                "accuracy": model["metrics"]["accuracy"],
                "artifact_bytes": artifact["length"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
