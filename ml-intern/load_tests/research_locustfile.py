"""One real OmniRoute chat and one distinct, verified model per Locust user."""

import os
import re
import threading
import time
import uuid
from pathlib import Path

import certifi
import gevent
from bson import ObjectId
from dotenv import load_dotenv
from helpers import (
    auth_headers,
    delete_session,
    login_user,
    register_user,
    send_chat_and_read_sse,
)
from locust import HttpUser, constant, events, task
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

if os.getenv("ENABLE_REAL_LLM_LOAD_TEST", "").lower() != "true":
    raise RuntimeError(
        "Set ENABLE_REAL_LLM_LOAD_TEST=true to run real OmniRoute traffic"
    )

EXPERIMENT_ID = os.getenv("EXPERIMENT_ID", time.strftime("%Y%m%d_%H%M%S"))
if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", EXPERIMENT_ID):
    raise ValueError(
        "EXPERIMENT_ID must have 1-24 letters, digits, underscores or hyphens"
    )

CASE = os.getenv("RESEARCH_DATASET", "iris").lower()
CASES = {
    "iris": (
        "Iris Species",
        "target",
        ("XGBClassifier", "RandomForestClassifier", "LogisticRegression"),
    ),
    "cancer": (
        "Breast Cancer Wisconsin (Diagnostic)",
        "target",
        ("XGBClassifier", "RandomForestClassifier", "LogisticRegression"),
    ),
    "california": (
        "California Housing",
        "MedHouseVal",
        ("XGBRegressor", "RandomForestRegressor", "LinearRegression"),
    ),
}
if CASE != "mixed" and CASE not in CASES:
    raise ValueError(f"RESEARCH_DATASET must be one of {sorted(CASES)} or mixed")
CASE_NAMES = tuple(CASES)
PROMPT_OPENINGS = (
    "Could you build a fresh {model_type} on {dataset_name} to predict {target}?",
    (
        "I have {dataset_name} ready in MongoDB. "
        "Please train a new {model_type} for the {target} column."
    ),
    (
        "Start a background training job for {dataset_name}: "
        "use {model_type} and predict {target}."
    ),
    (
        "For this experiment, create my own saved {model_type} model "
        "from {dataset_name}, targeting {target}."
    ),
    (
        "Can you fit {model_type} to the stored {dataset_name} data "
        "and return the training job? The label is {target}."
    ),
    (
        "Please queue one new {model_type} model for {dataset_name}. "
        "Its prediction target is {target}."
    ),
)

uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
kwargs = {"serverSelectionTimeoutMS": 5000, "maxPoolSize": 100}
if "+srv" in uri:
    kwargs["tlsCAFile"] = certifi.where()
mongo = MongoClient(uri, **kwargs)
db = mongo[os.getenv("MONGO_DB_NAME", "ml_intern")]
counter = 0
counter_lock = threading.Lock()


def next_number() -> int:
    global counter
    with counter_lock:
        counter += 1
        return counter


def record(name: str, started: float, error: str | None = None) -> None:
    events.request.fire(
        request_type="MODEL",
        name=name,
        response_time=(time.monotonic() - started) * 1000,
        response_length=0,
        exception=RuntimeError(error) if error else None,
    )


class DistinctModelUser(HttpUser):
    """Each virtual user asks once, waits for its saved artifact, then stays idle."""

    wait_time = constant(1)

    def on_start(self):
        self.number = next_number()
        self.prompt_variant = (self.number - 1) % len(PROMPT_OPENINGS)
        self.run_id = (
            f"exp_{EXPERIMENT_ID}_q{self.prompt_variant + 1}_{uuid.uuid4().hex[:16]}"
        )
        self.done = False
        self.password = os.getenv("RESEARCH_USER_PASSWORD", "ResearchLoad2026!")
        identity = f"research_{EXPERIMENT_ID}_{self.number}_{self.run_id[-8:]}"
        self.email = f"{identity}@loadtest.local"
        self.username = identity
        self.token = None

    @task
    def create_one_model(self):
        if self.done:
            gevent.sleep(3600)
            return
        self.done = True
        started = time.monotonic()
        session_id = None
        try:
            selected_case = (
                CASE_NAMES[(self.number - 1) % len(CASE_NAMES)]
                if CASE == "mixed"
                else CASE
            )
            dataset_name, target, models = CASES[selected_case]
            dataset = db.datasets.find_one(
                {"name": dataset_name}, sort=[("created_at", -1)]
            )
            if dataset is None:
                raise RuntimeError(
                    f"Dataset {dataset_name} is missing; run backend/seed_mongodb_datasets.py"
                )
            model_number = (
                (self.number - 1) // len(CASE_NAMES)
                if CASE == "mixed"
                else self.number - 1
            )
            model_type = models[model_number % len(models)]
            registered, _ = register_user(
                self.client, self.username, self.email, self.password
            )
            if not registered:
                raise RuntimeError("Registration failed")
            self.token = login_user(self.client, self.email, self.password)
            if not self.token:
                raise RuntimeError("Login failed")
            with self.client.post(
                "/api/session",
                json={"model": "openai/auto"},
                headers=auth_headers(self.token),
                name="/api/session [research]",
                catch_response=True,
            ) as response:
                if response.status_code != 200:
                    response.failure(f"Session HTTP {response.status_code}")
                    raise RuntimeError(f"Session HTTP {response.status_code}")
                session_id = response.json()["session_id"]
                if response.json().get("model") != "openai/auto":
                    response.failure("Session did not select OmniRoute")
                    raise RuntimeError("Session did not select OmniRoute")
                response.success()

            prompt = (
                PROMPT_OPENINGS[self.prompt_variant].format(
                    model_type=model_type, dataset_name=dataset_name, target=target
                )
                + f" The MongoDB dataset_id is {dataset['dataset_id']}. "
                "Use the queue_local_model_training tool exactly once with "
                f"run_id {self.run_id}, "
                f"dataset_id {dataset['dataset_id']}, model_type {model_type}, "
                f"and target_column {target}. Return its job ID."
            )
            _, _, terminal, _ = send_chat_and_read_sse(
                self.client,
                self.token,
                session_id,
                prompt,
                timeout=int(os.getenv("RESEARCH_CHAT_TIMEOUT_SECONDS", "600")),
                request_name="/api/chat [real model request]",
            )
            if terminal != "turn_complete":
                raise RuntimeError(f"Chat ended with {terminal}; no completed LLM turn")
            job = db.training_jobs.find_one({"run_id": self.run_id})
            if job is None:
                raise RuntimeError("LLM returned, but no training job was queued")
            if any(
                job.get(key) != value
                for key, value in (
                    ("dataset_id", dataset["dataset_id"]),
                    ("model_type", model_type),
                    ("target_column", target),
                )
            ):
                raise RuntimeError("Queued job does not match the requested training")
            record("llm_to_queued_job", started)
            delete_session(self.client, self.token, session_id)
            session_id = None

            deadline = time.monotonic() + int(
                os.getenv("RESEARCH_JOB_TIMEOUT_SECONDS", "7200")
            )
            while time.monotonic() < deadline:
                job = db.training_jobs.find_one({"run_id": self.run_id})
                if job["status"] == "failed":
                    raise RuntimeError(f"Worker failed: {str(job.get('error'))[:160]}")
                if job["status"] == "completed":
                    models_saved = list(
                        db.models.find({"run_id": self.run_id, "status": "ready"})
                    )
                    if len(models_saved) != 1:
                        raise RuntimeError(
                            f"Expected one saved model; found {len(models_saved)}"
                        )
                    model = models_saved[0]
                    if model["model_id"] != job.get("model_id"):
                        raise RuntimeError("Job model ID does not match saved model")
                    artifact = db.fs.files.find_one(
                        {"_id": ObjectId(model["gridfs_file_id"])}
                    )
                    if artifact is None:
                        raise RuntimeError("Saved model GridFS artifact is missing")
                    record("one_distinct_saved_model", started)
                    return
                gevent.sleep(10)
            raise RuntimeError("Training job timed out")
        except Exception as exc:
            record("one_distinct_saved_model", started, str(exc)[:250])
        finally:
            if session_id and self.token:
                delete_session(self.client, self.token, session_id)
