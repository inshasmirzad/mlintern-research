# ML Intern concurrency experiment record

Copy this file for each completed experiment. Keep the original Locust CSV/HTML files and the JSON printed by `verify_research_run.py`. Do not fill this template with estimates or guessed results.

## Setup

| Field | Value |
| --- | --- |
| Experiment ID | |
| Date and time (with timezone) | |
| Project revision or ZIP checksum | |
| Host CPU / RAM / OS | |
| Python / scikit-learn / XGBoost / Locust versions | |
| MongoDB version and location | |
| OmniRoute version, policy, and connected providers | |
| Dataset, target, and algorithms | |
| User target and spawn rate | |
| Worker lanes and ML train concurrency | |
| Provider quotas, if known | |

## Hypotheses

- **H1:** Moving fitting into a worker reduces chat-turn latency as the number of users grows, while queue wait increases once incoming jobs exceed worker throughput.
- **H2:** At high arrival rates, LLM provider errors or backend session pressure become visible before local training exhausts MongoDB capacity.
- **H3:** On Iris, all three algorithms produce valid multiclass models, but training time and artifact size differ. Do not infer a statistically superior algorithm from one hold-out split.

## Results

| Users | Spawn/s | Chat success % | Job queued % | Verified model % | Chat p95 s | End-to-end p95 s | Queue wait p95 s | Provider 429/5xx | Peak backend RAM | Notes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | | | | | | | | | | |
| 10 | | | | | | | | | | |
| 100 | | | | | | | | | | |
| 1000 | | | | | | | | | | |

| Algorithm | Dataset | Independent fits | Accuracy or R² (mean, range) | Macro F1 or RMSE (mean, range) | Fit time p95 s | Artifact bytes (median) |
| --- | --- | ---: | --- | --- | ---: | ---: |
| XGBClassifier | Iris | | | | | |
| RandomForestClassifier | Iris | | | | | |
| LogisticRegression | Iris | | | | | |

## Failure analysis

Record counts separately for registration/login, session creation, LLM turn, tool omission, job queue, worker fit, model metadata, and GridFS artifact. Include the exact Locust failure labels and relevant sanitized server messages. Note whether a retry used the same `run_id` and whether it reused the prior model.

## Interpretation

State what the measurements support, which resource was saturated first, and which alternative explanations remain. Report provider quotas and any missing telemetry. A model request that returned a chat response but saved no artifact is an end-to-end failure.
