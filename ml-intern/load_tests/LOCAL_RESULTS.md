# Local experiment record — 2026-10-15

These are measurements from one Windows laptop and local MongoDB, not a claim about general LLM capacity. Each virtual user registered, sent one real OmniRoute chat asking for a distinct model, and was counted as successful only when MongoDB contained the completed job, one model record, and its GridFS artifact. The worker used the seeded three-class Iris dataset.

| Experiment ID | Gateway route | Users | Distinct verified models | Result |
| --- | --- | ---: | ---: | --- |
| `pilot20261015b` | Existing gateway, `auto` | 1 | 1 | Passed; XGBoost accuracy and macro F1 both 0.9333 |
| `stage10a` | Existing gateway, `auto` | 10 | 0 | Failed on upstream 400/403/404 model errors |
| `stage10fresh` | Isolated Gemini gateway, `auto` | 10 | 6 | Four chats failed: the default auto pool still tried unavailable free models or hit a 503 |
| `pro1` | Isolated Gemini gateway, `auto/chat:pro` | 1 | 1 | Passed; XGBoost accuracy and macro F1 both 0.9333 |
| `stage10pro` | Isolated Gemini gateway, `auto/chat:pro` | 10 | 6 | All 10 chat turns failed, including after six jobs had been queued; route selected a Gemini TTS model without tool calling or hit a 503 queue limit |
| `stage10fixed` | Isolated Gemini gateway, `gemini/gemini-3.8-flash` | 10 | 2 | All 10 chat turns failed; the provider returned 503 queue-budget and credential-cooldown errors |
| `early1` | Fixed Gemini route with direct queue completion | 1 | 0 | Provider returned 503 queue-budget before the queue tool ran |

The isolated gateway uses a separate `DATA_DIR` and has one active Gemini connection. This preserved the prior OmniRoute database, whose encryption key was unavailable. The local backend uses `OMNIROUTE_BASE_URL=http://127.0.0.1:20129/v1` and `OMNIROUTE_ROUTE_MODEL=auto/chat:pro`. The private data directory and API credentials are outside the shareable ZIP.

The first four runs show why a reachable gateway and successful HTTP session creation are insufficient evidence of model creation. In `stage10fresh`, the six successful requests produced six distinct ready model records and six artifacts, while four failed before a training job was queued. Routing errors were visible in Locust's `*_failures.csv`; job and artifact counts came from `verify_research_run.py`. The `pro1` job took about 0.17 seconds waiting in the queue and 0.60 seconds fitting and saving. A single run does not estimate a latency distribution.

The resource monitor was started against `early1` for a short check and wrote timestamped CPU, RAM, process memory, job-status, and model-count rows to `load_tests/early1_monitor.csv`.

After the first five measurements, the queue tool was changed to finish the chat turn immediately after it returns a durable job ID. This removes an unnecessary second LLM call that had caused some turns to fail *after* the worker already saved their models. The `early1` retry could not reach the tool because the one connected account was cooling down. The changed turn needs a successful live pilot once provider capacity is available.

The next gate is a 10-user run pinned to `gemini/gemini-3.8-flash` after verifying the revised queue turn. This is a fixed-model baseline; it does not claim auto routing. If that passes, run 100 users, inspect provider quota and server memory, and then run 1,000 with the same recorded conditions. A result should report both LLM queue success and final saved-model success, plus provider errors and cost. OmniRoute can choose among available LLM models; its one connected Gemini account does not demonstrate balancing across multiple providers. A second working provider and a tool-capable candidate pool would be needed for that claim.
