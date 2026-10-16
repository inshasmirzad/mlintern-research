"""Run durable local MongoDB model-training jobs outside the chat server.

Start from the repository root: uv run --extra xgboost python scripts/training_worker.py
"""

import argparse
import asyncio
import logging
import os
import socket
import sys
import time
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import ReturnDocument

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from agent.tools.local_ml_tools import train_local_model_handler
from backend.database import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("training_worker")


async def process_one(worker_id: str, only_run_id: str | None = None) -> bool:
    db = get_db()
    selector = {"status": "queued"}
    if only_run_id:
        selector["run_id"] = only_run_id
    job = await db.training_jobs.find_one_and_update(
        selector,
        {
            "$set": {
                "status": "running",
                "started_at": time.time(),
                "worker_id": worker_id,
            }
        },
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if job is None:
        return False

    run_id = job["run_id"]
    log.info("Starting job %s (%s)", job["job_id"], job["model_type"])
    try:
        result, ok = await train_local_model_handler(
            {
                "dataset_id": job["dataset_id"],
                "model_type": job["model_type"],
                "target_column": job["target_column"],
                "force_retrain": True,
                "run_id": run_id,
            }
        )
        if not ok:
            raise RuntimeError(result[:1000])
        model = await db.models.find_one({"run_id": run_id, "status": "ready"})
        if model is None or not model.get("gridfs_file_id"):
            raise RuntimeError(
                "Training returned success without a saved model artifact"
            )
        artifact = await db.fs.files.find_one(
            {"_id": ObjectId(model["gridfs_file_id"])}
        )
        if artifact is None:
            raise RuntimeError(
                "Model metadata exists but its GridFS artifact is missing"
            )
        await db.training_jobs.update_one(
            {"_id": job["_id"], "status": "running"},
            {
                "$set": {
                    "status": "completed",
                    "model_id": model["model_id"],
                    "completed_at": time.time(),
                }
            },
        )
        log.info("Completed job %s as model %s", job["job_id"], model["model_id"])
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:1000]
        await db.training_jobs.update_one(
            {"_id": job["_id"], "status": "running"},
            {
                "$set": {
                    "status": "failed",
                    "error": message,
                    "completed_at": time.time(),
                }
            },
        )
        log.error("Failed job %s: %s", job["job_id"], message)
    return True


async def worker_loop(index: int) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{index}"
    while True:
        if not await process_one(worker_id):
            await asyncio.sleep(2)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recover-stale-seconds",
        type=int,
        default=0,
        help="Requeue jobs marked running longer than this many seconds; use only after the old worker stopped.",
    )
    args = parser.parse_args()
    lanes = max(1, int(os.getenv("ML_TRAIN_WORKERS", "2")))
    db = get_db()
    await db.command("ping")
    await db.training_jobs.create_index([("status", 1), ("created_at", 1)])
    if args.recover_stale_seconds > 0:
        recovered = await db.training_jobs.update_many(
            {
                "status": "running",
                "started_at": {"$lt": time.time() - args.recover_stale_seconds},
            },
            {"$set": {"status": "queued"}, "$unset": {"worker_id": ""}},
        )
        log.info("Requeued %d stale training jobs", recovered.modified_count)
    log.info("Connected to MongoDB; running %d worker lanes", lanes)
    await asyncio.gather(*(worker_loop(i) for i in range(lanes)))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Worker stopped; any interrupted job remains marked running")
