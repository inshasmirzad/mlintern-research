# ML Intern  research setup

This repository contains the complete source for the ML Intern web app and its local OmniRoute gateway. ML Intern has a React frontend, a FastAPI backend, a MongoDB training queue, a separate model-training worker, and Locust experiments. OmniRoute routes the chatbot's LLM calls and provides a live routing monitor. Model artifacts and dataset CSVs are created in MongoDB/GridFS when you run the project; credentials and local database files are not included.

The steps below use **Windows Command Prompt (`cmd.exe`)**. Open a separate Command Prompt for each terminal shown below. Replace `C:\path\to\mlintern-research` with the folder where you cloned this repository. Commands that start a service keep running until you press `Ctrl+C`.

## Repository layout

| Folder | Purpose |
| --- | --- |
| `ml-intern/backend/` | FastAPI server, authentication, and MongoDB dataset seeding |
| `ml-intern/frontend/` | React/Vite browser interface |
| `ml-intern/agent/` | Chat agent and training tools |
| `ml-intern/scripts/training_worker.py` | Fits queued models and stores them in MongoDB/GridFS |
| `ml-intern/load_tests/` | Real model-creation Locust test, resource monitor, audit, and experiment notes |
| `omniroute/` | OmniRoute source, router dashboard, and `npm run monitor` script |

ML Intern is derived from [Hugging Face's ML Intern](https://github.com/huggingface/ml-intern) under Apache-2.0. OmniRoute is derived from [diego souza's OmniRoute](https://github.com/diegosouzapw/OmniRoute) under MIT. The OmniRoute snapshot starts from upstream revision `2acbfc6fa6ef13e55552ce5bc3de45cbf2e535be` and includes local changes, including the router monitor. Keep the license files inside both folders when redistributing this project.

## 1. Install prerequisites

- Git.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.12 (`uv python install 3.12`).
- Node.js 24 and npm. OmniRoute's `package.json` also accepts Node 22.22.2 or newer in the Node 22 line.
- MongoDB, either through Docker Desktop or a local MongoDB server.
- At least one **working OmniRoute provider account that supports tool/function calls**. Provider accounts, rate limits, and API keys are personal; they are not part of this repository.

Clone the private repository using an account with access:

```bat
git clone https://github.com/inshasmirzad/mlintern-research.git
cd /d mlintern-research
```

Verify the installed runtimes:

```bat
git --version
uv --version
node --version
npm --version
docker --version
```

If you installed MongoDB locally rather than Docker, `docker --version` is optional.

## 2. Prepare dependencies and private configuration

### OmniRoute

```bat
cd /d C:\path\to\mlintern-research\omniroute
npm ci
copy .env.example .env
notepad .env
```

In `omniroute\.env`, set `INITIAL_PASSWORD` to a new password. Generate **separate** random values for `JWT_SECRET`, `API_KEY_SECRET`, and `STORAGE_ENCRYPTION_KEY`. For each value, run `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"` and paste the result into `.env`. Set `REQUIRE_API_KEY=true`, `PORT=20128`, and `BASE_URL=http://localhost:20128`. Keep the encryption key: the gateway needs the **same key** to read its existing encrypted provider credentials after a restart.

### ML Intern

```bat
cd /d C:\path\to\mlintern-research\ml-intern
uv python install 3.12
uv sync --extra xgboost --extra benchmark
copy .env.example .env
notepad .env
```

In `ml-intern\.env`, replace `JWT_SECRET_KEY` with another random value from the same Node command. Set `OMNIROUTE_BASE_URL` to the OmniRoute address, normally `http://127.0.0.1:20128/v1`. After creating a gateway API key in the OmniRoute dashboard, paste it into `OMNIROUTE_API_KEY`. Start with `OMNIROUTE_ROUTE_MODEL=auto`; once you know a connected model supports tool calls, you can set this to that model ID or to an OmniRoute combo name. Restart the ML Intern backend after changing this file.

### Frontend

```bat
cd /d C:\path\to\mlintern-research\ml-intern\frontend
npm ci
```

## 3. Start the services in separate terminals

### Terminal 1 — MongoDB

With Docker Desktop running:

```bat
docker run -d --name mlintern-mongo -p 27017:27017 -v mlintern_mongo_data:/data/db mongo:8
```

On later days, use `docker start mlintern-mongo`. If MongoDB is installed as a Windows service, use `net start MongoDB` instead. The ML Intern `MONGO_URI` must point to whichever MongoDB instance you started.

### Terminal 2 — OmniRoute gateway

```bat
cd /d C:\path\to\mlintern-research\omniroute
npm run dev
```

Open <http://127.0.0.1:20128/>. Sign in with your `INITIAL_PASSWORD`, add and test at least one provider connection, and create a gateway API key. Put that gateway key in `ml-intern\.env`. A provider showing as connected still needs enough quota to handle the experiment. Do a one-user model request before increasing the load.

### One-time dataset seeding

Run this **once** after MongoDB starts. It creates Iris (three-class classification), Breast Cancer Wisconsin (binary classification), and California Housing (regression) in MongoDB/GridFS. California Housing may need an internet connection on the first download.

```bat
cd /d C:\path\to\mlintern-research\ml-intern
uv run --extra xgboost python backend\seed_mongodb_datasets.py
```

### Terminal 3 — ML Intern backend

```bat
cd /d C:\path\to\mlintern-research\ml-intern
uv run --extra xgboost uvicorn main:app --app-dir backend --host 127.0.0.1 --port 7860
```

Check <http://127.0.0.1:7860/api/health/ready>. If port 7860 is already occupied, stop the older backend process before starting another one.

### Terminal 4 — training worker

```bat
cd /d C:\path\to\mlintern-research\ml-intern
set ML_TRAIN_WORKERS=2
set ML_TRAIN_MAX_CONCURRENT=2
uv run --extra xgboost python scripts\training_worker.py
```

The worker must stay open to turn queued jobs into saved models. Two worker lanes are a starting point for a laptop; increase them only after measuring CPU and memory.

### Terminal 5 — React frontend

```bat
cd /d C:\path\to\mlintern-research\ml-intern\frontend
set BACKEND_URL=http://127.0.0.1:7860
npm run dev
```

Open <http://127.0.0.1:5173/>. Register or log in, then ask: “Train a new XGBClassifier on the Iris Species dataset to predict the target column. Save the model and give me the job ID.” The job is asynchronous; the worker saves the model afterward. Iris is classification; use California Housing with target `MedHouseVal` for regression.

## 4. Watch OmniRoute routing

### Terminal 6 — router monitor

```bat
cd /d C:\path\to\mlintern-research\omniroute
set OMNIROUTE_MONITOR_BASE_URL=http://127.0.0.1:20128
npm run monitor
```

The monitor refreshes recent **completed** routing decisions, including selected provider/model, status, latency, retries, and fallback. It reads `/v1/explain/routing`; it is not a live in-flight request count. If your gateway runs on port 20129, set `OMNIROUTE_MONITOR_BASE_URL=http://127.0.0.1:20129` instead. Stop with `Ctrl+C`.

## 5. Run the real model-creation experiment

Start with one user, then six. Locust makes **one real OmniRoute chat request per virtual user**. Each request asks ML Intern to queue one unique model. Locust verifies a completed LLM turn, a matching training job, one ready model, and its GridFS artifact. The six question wordings rotate; `RESEARCH_DATASET=mixed` rotates Iris, cancer, and California datasets and their compatible algorithms. This uses real provider quota and can incur cost.

### Terminal 7 — Locust pilot

```bat
cd /d C:\path\to\mlintern-research\ml-intern
set ENABLE_REAL_LLM_LOAD_TEST=true
set RESEARCH_DATASET=mixed
set EXPERIMENT_ID=pilot6
uv run --extra benchmark locust -f load_tests\research_locustfile.py --host http://127.0.0.1:7860 --headless --users 6 --spawn-rate 1 --run-time 20m --csv load_tests\pilot6
```

Use a **new** `EXPERIMENT_ID` for each new run. Six virtual users exercise all three datasets and all six wordings; to exercise all three algorithms on each dataset, use at least nine users. If you want the Locust web dashboard, omit `--headless` and `--run-time`, then open <http://127.0.0.1:8089/> and enter the user count and spawn rate.

### Terminal 8 — resource and queue monitor

Start this before Locust. Its experiment ID must match the Locust terminal:

```bat
cd /d C:\path\to\mlintern-research\ml-intern
uv run --extra benchmark python scripts\monitor_research.py --experiment-id pilot6
```

It writes `ml-intern\load_tests\pilot6_monitor.csv` every five seconds with host and process memory, CPU, job states, and saved-model count. Stop it with `Ctrl+C` after the worker finishes.

### Final audit

```bat
cd /d C:\path\to\mlintern-research\ml-intern
uv run python load_tests\verify_research_run.py --experiment-id pilot6 --expected-users 6
```

See [the detailed research procedure](ml-intern/load_tests/RESEARCH.md) for metrics, larger stages, limits, and the experiment record template. The older `ml-intern/load_tests/locustfile.py` is a lightweight chat test; use `research_locustfile.py` for model creation.

## Scaling and interpreting failures

Increase from 1 to 6 to 10 and beyond only after the previous stage completes. A 1,000-user Locust setting means 1,000 active virtual clients, not necessarily 1,000 simultaneous upstream LLM calls. `--spawn-rate` controls arrivals. Registration, provider calls, MongoDB, and CPU training each have separate limits. Queue-budget `503`, upstream `429`, and connection timeouts are capacity failures; the `MODEL` failure for the same user is the end-to-end consequence, not an additional independent request. At high loads, pre-registering users would be needed to isolate model-creation throughput from authentication throughput. Do not report an experiment as 1,000 successful models until the final audit confirms 1,000 distinct artifacts.

## Sharing and security

The repository contains source and lockfiles, not provider credentials, private `.env` files, MongoDB data, session logs, or generated trained models. Each person configures their own provider account and secrets. A private GitHub repository still requires access management; do not paste credentials into issues or commit them later. Generated model artifacts remain in the local MongoDB instance unless separately exported.
