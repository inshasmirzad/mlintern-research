"""Record process memory, host load, and MongoDB queue depth during a run."""

import argparse
import csv
import os
import re
import time
from pathlib import Path

import certifi
import psutil
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def process_memory() -> dict[str, int]:
    memory = {"backend_rss_bytes": 0, "worker_rss_bytes": 0, "omniroute_rss_bytes": 0}
    for process in psutil.process_iter(["cmdline", "memory_info"]):
        try:
            command = " ".join(process.info["cmdline"] or []).lower()
            rss = process.info["memory_info"].rss
        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            continue
        if "uvicorn main:app" in command:
            memory["backend_rss_bytes"] += rss
        elif "training_worker.py" in command:
            memory["worker_rss_bytes"] += rss
        elif "omniroute" in command and "node" in command:
            memory["omniroute_rss_bytes"] += rss
    return memory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--interval-seconds", type=float, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", args.experiment_id):
        parser.error("Invalid experiment ID")
    if args.interval_seconds <= 0:
        parser.error("Interval must be positive")
    output = args.output or ROOT / "load_tests" / f"{args.experiment_id}_monitor.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    kwargs = {"serverSelectionTimeoutMS": 5000}
    if "+srv" in uri:
        kwargs["tlsCAFile"] = certifi.where()
    db = MongoClient(uri, **kwargs)[os.getenv("MONGO_DB_NAME", "ml_intern")]
    db.command("ping")
    selector = {"run_id": {"$regex": "^" + re.escape(f"exp_{args.experiment_id}_")}}
    fields = [
        "timestamp_utc",
        "host_cpu_percent",
        "host_ram_used_bytes",
        "backend_rss_bytes",
        "worker_rss_bytes",
        "omniroute_rss_bytes",
        "queued",
        "running",
        "completed",
        "failed",
        "saved_models",
    ]
    psutil.cpu_percent(interval=None)
    print(f"Writing {output}; press Ctrl+C to stop")
    try:
        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            while True:
                counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
                for item in db.training_jobs.aggregate(
                    [
                        {"$match": selector},
                        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                    ]
                ):
                    if item["_id"] in counts:
                        counts[item["_id"]] = item["count"]
                row = {
                    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "host_cpu_percent": psutil.cpu_percent(interval=None),
                    "host_ram_used_bytes": psutil.virtual_memory().used,
                    **process_memory(),
                    **counts,
                    "saved_models": db.models.count_documents(selector),
                }
                writer.writerow(row)
                stream.flush()
                time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print(f"Stopped monitor; data saved to {output}")


if __name__ == "__main__":
    main()
