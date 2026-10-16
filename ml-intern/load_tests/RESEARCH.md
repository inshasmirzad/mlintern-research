# Real model creation load experiment

This experiment makes **one real chat request through OmniRoute per virtual user**. Each request asks ML Intern to queue one training job with a unique `run_id`. A separate worker fits a fresh model from a MongoDB dataset and saves the artifact in GridFS. Locust counts end-to-end success only after it finds exactly one matching ready model and its artifact. The original `load_tests/locustfile.py` remains available for the earlier lightweight chat test.

When the LLM calls only `queue_local_model_training` and the tool succeeds, ML Intern returns the job ID directly as the assistant response. This avoids a second provider call just to restate the queue result. If the gateway fails before the tool call, no job is counted. If the worker fails later, the Locust saved-model metric fails even though the chat succeeded.

## What is being measured

The path is `Locust user → registration/login → ML Intern session → OmniRoute LLM → queue_local_model_training tool → MongoDB training_jobs → training_worker.py → models metadata + GridFS artifact`.

- **LLM success:** a completed chat turn also created a job with the requested dataset, model, target and `run_id`.
- **Training success:** that job completed and exactly one saved model plus its GridFS artifact exists for the `run_id`.
- **Concurrency:** `--users 1000` means 1,000 virtual clients can be active. `--spawn-rate` controls how quickly they arrive. The worker's `ML_TRAIN_WORKERS` and `ML_TRAIN_MAX_CONCURRENT` bound simultaneous CPU fits. OmniRoute routes the LLM requests; it does not distribute scikit-learn/XGBoost training.
- **Metrics:** Locust reports request latency, requests/second, and failures. The audit reports queued/completed/failed jobs, distinct models, artifacts, and job duration percentiles. For Iris and cancer, model quality uses held-out accuracy, macro F1, and balanced accuracy. For California Housing, it uses R², RMSE, and MAE; regression has no classification accuracy.

Each user trains a separate model, even if the same dataset and algorithm were used earlier. Deterministic algorithms can produce identical predictions or weights on the same fixed split; “distinct” here means a separate fit, model record, and artifact. Six differently worded model-creation questions rotate across users; every question still gives the exact dataset, algorithm, target, and unique `run_id` so its result can be verified. The `q1` through `q6` segment in each `run_id` identifies the wording used. The training pipeline imputes numeric and categorical features using the training split, one-hot encodes categories, and preserves original class labels in saved classifiers. The default `RESEARCH_DATASET=iris` case rotates XGBoost, random forest, and logistic regression on Iris, a three-class dataset. Set `RESEARCH_DATASET=cancer` for binary classification or `california` for regression. Set `RESEARCH_DATASET=mixed` to rotate all three datasets across users; each dataset also rotates its three algorithms. At least three users are needed to include every dataset; six exercise all question wordings. California jobs are much more expensive in CPU time and artifact size.

## One-time setup

Use Windows PowerShell. Replace `C:\path\to\mlintern` with the extracted project folder. The folder must contain `pyproject.toml`. Keep `.env` private and set `MONGO_URI` to the local MongoDB server used by the backend. Start MongoDB before running the following checks. Install Node.js/npm and OmniRoute, then connect a working provider in the OmniRoute dashboard at <http://localhost:20128/>. If the gateway requires authentication, create a gateway API key there and set `OMNIROUTE_API_KEY` in the root `.env` before starting the backend. The selected ML Intern model is explicitly `openai/auto`.

```powershell
cd C:\path\to\mlintern
uv sync --extra xgboost --extra benchmark
npm install -g omniroute
```

If the three datasets are not already present in this MongoDB database, seed them **once**:

```powershell
cd C:\path\to\mlintern
uv run --extra xgboost python backend/seed_mongodb_datasets.py
```

This local smoke test creates one real Iris XGBoost model through the queue and worker, without calling an LLM:

```powershell
cd C:\path\to\mlintern
uv run --extra xgboost python scripts/smoke_training_job.py
```

## Terminals for the real LLM run

Open separate PowerShell windows and leave terminals 1–3 running. The React frontend is optional because Locust talks directly to FastAPI. Start the monitor before Locust if you want host and queue measurements.

| Terminal | `cd` | Command |
| --- | --- | --- |
| 1: OmniRoute | Any folder | `omniroute serve --port 20128` |
| 2: ML Intern backend | `cd C:\path\to\mlintern` | `uv run --extra xgboost uvicorn main:app --app-dir backend --host 127.0.0.1 --port 7860` |
| 3: training worker | `cd C:\path\to\mlintern` | `$env:ML_TRAIN_WORKERS='2'; $env:ML_TRAIN_MAX_CONCURRENT='2'; uv run --extra xgboost python scripts/training_worker.py` |
| 4: Locust | `cd C:\path\to\mlintern` | Use one of the commands below. |
| 5: resource monitor | `cd C:\path\to\mlintern` | `uv run --extra benchmark python scripts/monitor_research.py --experiment-id iris1000a` (use the same ID as Locust) |

The backend should respond at <http://127.0.0.1:7860/api/health/ready>. A working OmniRoute provider, gateway key when required, and provider rate limits determine how many real LLM calls succeed.

If OmniRoute reports that an existing `storage.sqlite` needs `STORAGE_ENCRYPTION_KEY`, restore the **original** key in `%USERPROFILE%\.omniroute\.env` before testing saved provider connections. Generating a different key does not decrypt that database. The gateway API key for ML Intern belongs in the project `.env` as `OMNIROUTE_API_KEY`; these are different credentials.

If the old encryption key is unavailable, leave the old database untouched and start OmniRoute with a new `DATA_DIR`. Connect a working provider in the new dashboard. For this machine, the isolated research gateway uses `%USERPROFILE%\.omniroute-mlintern-research2` on port `20129`, while the existing development gateway retains port `20128`; the project `.env` points to `OMNIROUTE_BASE_URL=http://127.0.0.1:20129/v1`. The private research data directory and its `.env` must stay outside the shared ZIP. When launching the isolated gateway in a new PowerShell window, set `DATA_DIR`, `STORAGE_ENCRYPTION_KEY`, `INITIAL_PASSWORD`, and `JWT_SECRET` from that private `.env`, then run `omniroute serve --port 20129`. Start the backend after setting `OMNIROUTE_BASE_URL`.

Before scaling, make one direct chat completion with `model=auto` against the intended OmniRoute port and confirm the selected provider works. Then run one Locust user and audit its saved artifact. A successful `/v1/models` response proves the gateway is reachable but does not prove a provider can complete a tool-calling chat. If a stage fails with upstream 400/403/404/429 errors, inspect `load_tests/<experiment-id>_failures.csv`, repair the provider connection or quota, and rerun with a new experiment ID. OmniRoute's default `auto` pool may try uncredentialed free models; set `OMNIROUTE_ROUTE_MODEL=auto/chat:pro` in the project `.env` to restrict the pool to premium chat models, then restart the backend. Check the gateway's `/v1/auto-combo/chat:pro/candidates` endpoint to see its candidates. A filtered route still needs a working account and enough quota. Do not count HTTP 200 for an SSE connection as an LLM success: Locust's `llm_to_queued_job` metric and the MongoDB audit verify the completed turn and queued job.

For a fixed-model control, set `OMNIROUTE_ROUTE_MODEL=gemini/gemini-3.8-flash` when that model is available on your connected Gemini account. Verify a direct **tool-calling** completion first, because a text-only response can pass for a model that rejects tools. This control still sends every LLM request through OmniRoute but does not measure model switching. The local `auto/chat:pro` trial selected a text-to-speech model without function calling, so a candidate list containing only paid models is insufficient for this ML assistant.

Start with one real user. Each stage uses a **new** `EXPERIMENT_ID`, which lets the audit isolate its jobs and artifacts. Do not reuse an ID for a different run.

If using Windows Command Prompt (`cmd.exe`) rather than PowerShell, use `set` for environment variables. This three-user mixed pilot exercises all seeded datasets:

```bat
cd C:\path\to\mlintern
set ENABLE_REAL_LLM_LOAD_TEST=true
set EXPERIMENT_ID=mixed_%RANDOM%_%RANDOM%
set RESEARCH_DATASET=mixed
uv run --extra benchmark locust -f load_tests/research_locustfile.py --host http://127.0.0.1:7860 --headless --users 3 --spawn-rate 1 --run-time 20m
```

```powershell
cd C:\path\to\mlintern
$env:ENABLE_REAL_LLM_LOAD_TEST='true'
$env:EXPERIMENT_ID='pilot1'
$env:RESEARCH_DATASET='iris'
uv run --extra benchmark locust -f load_tests/research_locustfile.py --host http://127.0.0.1:7860 --headless --users 1 --spawn-rate 1 --run-time 15m --csv load_tests/pilot1
```

Then measure 10, 100 and 1,000 users with new IDs. Change only the three values shown for each stage; keep the backend, provider, worker, dataset, and machine configuration recorded in your notes. Example full run:

```powershell
cd C:\path\to\mlintern
$env:ENABLE_REAL_LLM_LOAD_TEST='true'
$env:EXPERIMENT_ID='iris1000a'
$env:RESEARCH_DATASET='iris'
uv run --extra benchmark locust -f load_tests/research_locustfile.py --host http://127.0.0.1:7860 --headless --users 1000 --spawn-rate 10 --run-time 3h --csv load_tests/iris1000a --html load_tests/iris1000a.html
```

Locust will keep users alive after their single request, so a target of 1,000 users creates at most 1,000 distinct training requests. The run finishes when its `--run-time` expires; inspect the audit after the worker has drained the queue. For a live Locust dashboard, omit `--headless` and `--run-time`, then open <http://localhost:8089/> and enter the user count and spawn rate. The original simple-question test is a different file and does not measure model creation.

The monitor writes `load_tests/<experiment-id>_monitor.csv` every five seconds with host CPU/RAM, backend/worker/OmniRoute memory, job status counts, and saved-model count. Stop it with `Ctrl+C` after the worker finishes.

Audit the final result from a separate terminal:

```powershell
cd C:\path\to\mlintern
uv run python load_tests/verify_research_run.py --experiment-id iris1000a --expected-users 1000
```

Exit code 0 means 1,000 jobs each have one matching model and GridFS artifact. A nonzero exit means the goal was not reached; inspect `job_statuses`, `missing_queued_jobs`, artifact errors, and Locust's `*_failures.csv`. For live progress, rerun the audit while the worker operates; it will exit nonzero until complete. A crashed worker can leave jobs marked `running`. After stopping the old worker, restart it with `--recover-stale-seconds 300` to requeue jobs that have been running longer than five minutes. Use a higher age if a single fit can exceed five minutes.

## Research questions and controls

1. **Where is the first bottleneck?** Compare 1, 10, 100 and 1,000 users. Record Locust `llm_to_queued_job` p50/p95/p99, queue success rate, end-to-end model success rate, queue wait (`started_at - created_at`), fit+save time (`completed_at - started_at`), total job time, backend memory/CPU, MongoDB disk use, and OmniRoute provider status/rate-limit responses. The plain `/api/chat` HTTP time is only the SSE connection time; it is not LLM generation latency. Time to first token and per-token latency need additional provider or SSE instrumentation.
2. **What does routing change?** Repeat at the same load with one fixed provider and with OmniRoute auto routing when the gateway supports both. Keep the prompt, dataset, worker count, and spawn rate the same. Record which provider handled each call if OmniRoute exposes that data. Report costs and provider 429/5xx errors; do not claim balancing merely because `openai/auto` was selected.
3. **What does asynchronous training change?** Compare the original direct `train_local_model` path with this queue path at small loads. The queue moves CPU work out of the chat server so LLM turns can finish before fitting. It can still accumulate backlog if arrival rate exceeds worker throughput.
4. **How good are the models?** On Iris, compare held-out accuracy and macro F1 for XGBoost, random forest, and logistic regression. On California, compare R²/RMSE/MAE. These are fixed 80/20 hold-out scores; use cross-validation or a separate final test set before making a broad “best model” claim. The `get_best_local_model` tool ranks saved models for a dataset by the stored held-out score.

Use [the experiment record template](EXPERIMENT_TEMPLATE.md) to keep the experiment ID, start/end time, dataset, target, algorithms, Git/archive version, Python and package versions, machine CPU/RAM, MongoDB storage, OmniRoute version/providers, spawn rate, worker lanes, provider limits, and any interruptions. A 1,000-client result on one laptop is a measurement of this deployment, not a universal LLM capacity figure.

## References

- [ORCA: A Distributed Serving System for Transformer-Based Generative Models (OSDI 2022)](https://www.usenix.org/conference/osdi22/presentation/yu) is the primary conference reference for concurrent LLM serving. It studies iteration-level scheduling and batching inside a model-serving system. Use it to frame the distinction between 1,000 client sessions and the number of requests a provider can actually serve concurrently; ML Intern and OmniRoute do not implement ORCA's scheduler.
- [DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving (OSDI 2024)](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin) motivates measuring time to first token and per-token latency under load. OmniRoute is a gateway to upstream providers, so those internal serving phases are not directly controlled by this project.
- [Locust distributed runs](https://docs.locust.io/en/stable/running-distributed.html) and [high request rates](https://docs.locust.io/en/stable/increasing-request-rate.html): options if one load generator becomes the bottleneck.
- [Locust request failure reporting](https://docs.locust.io/en/latest/writing-a-locustfile.html): why this scenario marks model verification separately from HTTP status.
- [FastAPI background work](https://fastapi.tiangolo.com/tutorial/background-tasks/): rationale for a durable external worker for costly training.
- [XGBoost Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html) and [scikit-learn metrics](https://scikit-learn.org/stable/api/sklearn.metrics.html): algorithms and evaluation definitions.
