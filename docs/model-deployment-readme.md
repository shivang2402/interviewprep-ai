# Model Deployment — InterviewPrep AI

This document covers the Model Deployment phase of the project: where the model runs, how it is automatically deployed from this repository, how it is monitored in production, and how retraining / corpus refresh is triggered when drift or performance degradation is detected.

---

## 1. Deployment Strategy

**Type: Cloud Deployment**

| Item | Value |
|---|---|
| Cloud Provider | Google Cloud Platform (GCP) |
| Region | `us-central1` |
| Serving Service | **Cloud Run** (fully managed containers) for the retrieval-augmented backend and the Next.js frontend |
| Model Registry | **Vertex AI Model Registry** (retrieval configs registered by `eval_pipeline.yml`) |
| Database | **Cloud SQL** for PostgreSQL 15 with `pgvector` extension |
| Image Registry | **Artifact Registry** (`interviewprep-ai` repo) |
| Secret Storage | **Secret Manager** (`db-password`, `db-user`, `openai-api-key`) |
| IaC | **Terraform** (`terraform/*.tf`) |
| CI/CD | **GitHub Actions** (`.github/workflows/*.yml`) |
| Monitoring | **Google Cloud Monitoring** (alerts), **MLflow** (experiments / drift reports), **Evidently AI** (data drift) |

Edge deployment is not used — the model serves queries interactively via a REST API, and the retrieval stack (embedding model + pgvector + reranker) is not suitable for resource-constrained edge devices. All model-optimization work is therefore captured in the eval pipeline (Section 6), not in quantization/pruning.

### Live Endpoints

| Service | URL |
|---|---|
| Frontend | https://interviewprep-frontend-21181283814.us-central1.run.app |
| Backend API | https://interviewprep-backend-21181283814.us-central1.run.app |
| Health Check | https://interviewprep-backend-21181283814.us-central1.run.app/api/health |

---

## 2. GCP Services & Configuration

All cloud infrastructure is provisioned by Terraform modules under `terraform/`.

### Cloud Run services

| Service | CPU | Memory | Min → Max | Port |
|---|---|---|---|---|
| `interviewprep-backend` (FastAPI + RAG) | 2 | 2 Gi | 1 → 10 | 8000 |
| `interviewprep-frontend` (Next.js) | 1 | 512 Mi | 0 → 5 | 3000 |

Defined in `terraform/cloud_run.tf`.

### Cloud SQL

- Instance: `interviewprep-ai-db` (see `terraform/cloud_sql.tf`)
- Tier: `db-custom-2-7680` (2 vCPU, 7.5 GB RAM)
- PostgreSQL 15, `pgvector` extension, 20 GB SSD (autoresize), regional HA
- Backend connects via Cloud SQL socket in production (`DB_CONNECTION_MODE=socket`), TCP locally

### Artifact Registry

- Repo: `interviewprep-ai` (Docker format)
- Images pushed by `deploy.yml`: `us-central1-docker.pkg.dev/<project>/interviewprep-ai/{backend,frontend}:<sha>`

### Cloud Monitoring Alert Policies (`terraform/monitoring.tf`)

| Alert | Threshold | Window |
|---|---|---|
| Backend 5xx error rate | > 5 % | 5 min |
| Backend p95 latency | > 5 s | 5 min |

Both notify via email notification channel.

---

## 3. Deployment Automation (CI/CD)

All deployment is driven by GitHub Actions — no manual `gcloud run deploy` is required to update production.

| Workflow | Trigger | Purpose |
|---|---|---|
| `deploy.yml` | push to `dev`, manual | Build backend + frontend images, push to Artifact Registry, deploy to Cloud Run, post-deploy health check |
| `eval_pipeline.yml` | push to `main` when `src/evaluation/retrieval_model_configs.yaml` changes | Evaluate retrieval configs on the golden set, register best config in **Vertex AI Model Registry** (aliases: `latest`, `production`) |
| `drift_detection.yml` | cron `Mon 09:00 UTC`, manual | Composite embedding drift (centroid + per-dim p95 + Evidently KS); dispatches `corpus_refresh.yml` on breach |
| `weekly_performance_check.yml` | cron `Mon 10:00 UTC`, manual | Standalone Evidently drift on query embeddings; dispatches `corpus_refresh.yml` if > 30 % dims drift |
| `corpus_refresh.yml` | `workflow_dispatch` (manual or from the two jobs above) | Refresh corpus via Airflow DAG, run regression gate, notify via Slack + SMTP |
| `ci.yml` | push / PR to `main` | pytest with 80 % coverage gate |

### `deploy.yml` at a glance

1. Auth to GCP using `GCP_SA_KEY` service-account secret
2. `docker buildx` → push `backend` and `frontend` images to Artifact Registry tagged with the commit SHA
3. `gcloud run deploy` for each service, injecting env vars and Secret Manager references
4. `curl` the `/api/health` endpoint to verify the revision is healthy before promoting traffic
5. Post a deployment-status notification

The model itself is packaged inside the backend image — the `all-MiniLM-L6-v2` SentenceTransformer is pre-downloaded during the Docker build and the container runs with `HF_HUB_OFFLINE=1` so no weights are fetched at cold start.

---

## 4. Connection to Repository

- `deploy.yml` runs automatically on every push to `dev` — merging a PR to `dev` ships it to Cloud Run.
- `eval_pipeline.yml` runs when retrieval config changes land on `main`, closing the loop between model code and Vertex AI Model Registry.
- Monitoring workflows (`drift_detection.yml`, `weekly_performance_check.yml`) use `gh workflow run` / `peter-evans/repository-dispatch` to call back into GitHub and trigger `corpus_refresh.yml` when thresholds are breached.

Required GitHub secrets (set at repo level):

```
GCP_SA_KEY                    # service-account JSON
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
MLFLOW_HOST
BACKEND_SERVICE_URL, FRONTEND_SERVICE_URL
AIRFLOW_API_URL, AIRFLOW_API_TOKEN
SLACK_WEBHOOK_URL             # optional (notifications skipped if unset)
SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD   # optional
```

---

## 5. Replication Steps (Fresh Environment)

### Prerequisites

- `gcloud` CLI authenticated (`gcloud auth login`, `gcloud auth application-default login`)
- Terraform ≥ 1.5
- Docker (local build / compose)
- A GCP project with billing enabled and the following APIs enabled: Cloud Run, Cloud SQL Admin, Artifact Registry, Secret Manager, Vertex AI, Cloud Monitoring, IAM

### Step-by-step

1. **Clone & configure**

   ```bash
   git clone <repo-url>
   cd interviewprep-ai
   cp .env.example .env        # fill DB creds + OPENAI_API_KEY if running locally
   ```

2. **Provision infrastructure (one-time, per GCP project)**

   ```bash
   cd terraform
   terraform init
   terraform apply \
     -var="project_id=<YOUR_PROJECT>" \
     -var="region=us-central1"
   ```

   This creates Cloud SQL, Artifact Registry, Secret Manager entries, Cloud Run services (empty placeholders), IAM bindings, and Cloud Monitoring alert policies.

3. **Populate secrets**

   ```bash
   gcloud secrets versions add db-password    --data-file=- <<< "$DB_PASSWORD"
   gcloud secrets versions add db-user        --data-file=- <<< "$DB_USER"
   gcloud secrets versions add openai-api-key --data-file=- <<< "$OPENAI_API_KEY"
   ```

4. **Add GitHub secrets** (Settings → Secrets and variables → Actions) per the list in Section 4.

5. **First deployment** — push to `dev`:

   ```bash
   git checkout dev && git push origin dev
   ```

   `deploy.yml` builds both images, pushes to Artifact Registry, deploys to Cloud Run, and runs the health check.

6. **Seed the corpus** — trigger the Airflow scraping pipeline (or run `corpus_refresh.yml` manually from the Actions tab) to populate the `pgvector`-backed `chunks` table.

7. **Verify deployment**

   ```bash
   curl https://interviewprep-backend-21181283814.us-central1.run.app/api/health
   # → {"status":"ok"}

   curl -X POST .../api/query \
     -H 'Content-Type: application/json' \
     -d '{"query":"What is a B-tree?"}'
   ```

   Or open the frontend URL and run a query through the UI.

### Local replication (`docker-compose`)

```bash
docker compose up --build
# db (pgvector:pg15) :5432  →  backend :8000  →  frontend :3000
```

Services defined in `docker-compose.yml`: `db` (pgvector/pg15), `backend`, `frontend`.

---

## 6. Model Monitoring & Triggering Retraining

### 6.1 Performance monitoring

- **MLflow** tracks every evaluation run from `eval_pipeline.yml` — NDCG@10, Recall@10, MRR@5, `selection_score`, bias metrics. Artifacts (plots, drift HTMLs) are uploaded to GCS.
- **Cloud Monitoring** alert policies (Section 2) fire on 5xx rate and p95 latency.
- `src/monitoring/performance_monitor.py` compares live `selection_score` against the deployed baseline once a week.

### 6.2 Data-shift detection

`src/monitoring/drift_detection.py` pulls the last 7 days of query embeddings from the `query_logs` table and computes:

- Centroid cosine distance vs. the reference distribution built by `build_reference_distribution.py`
- Per-dimension normalized mean shift (p95 across the 384 `all-MiniLM-L6-v2` dims)
- **Evidently AI** `DataDriftPreset` (Kolmogorov–Smirnov test per dimension)

Reports (HTML + JSON) are logged to MLflow and uploaded to GCS.

### 6.3 Retraining thresholds

Version-controlled in `src/evaluation/retraining_thresholds.yaml`:

```yaml
performance_degradation_pct: 0.03   # 3 % drop in selection_score vs. baseline
evidently_drift_pct:         0.30   # 30 % of embedding dims drifted
```

When any threshold is breached, the monitoring workflow dispatches `corpus_refresh.yml`.

### 6.4 Automated retraining pipeline (`corpus_refresh.yml`)

1. **Snapshot** the currently deployed `selection_score` from MLflow
2. **Pull new data** — trigger the Airflow `interview_scraping_pipeline` DAG, which chains into `chunking_embedding_pipeline` (re-scrape → re-chunk → re-embed → re-index in `pgvector`)
3. **Re-evaluate** — `PipelineOrchestrator` runs the retrieval configs against the refreshed corpus on the golden set
4. **Regression gate** — if the new `selection_score` drops by more than `0.005` vs. the snapshot, the run is tagged `aborted_regression` and the existing corpus is kept
5. **Promote** — if the gate passes, the refresh is tagged `refreshed`; the backend serves the new corpus on the next request (the corpus lives in Cloud SQL, so no container redeploy is required)
6. **Model-config changes** (as opposed to corpus changes) land via PR → `eval_pipeline.yml` on merge → Vertex AI Model Registry version bump → `deploy.yml` on next push to `dev`

### 6.5 Notifications

Implemented in `corpus_refresh.yml`:

- **Slack** via `SLACK_WEBHOOK_URL` — posts the run outcome (`refreshed` / `aborted_regression` / `dag_failed`) with links to the MLflow run and GitHub Actions log
- **Email** via SMTP — team distribution list

Notification steps are guarded on secret presence, so they skip cleanly if `SLACK_WEBHOOK_URL` / SMTP secrets are not set in a fork.

---

## 7. Logs & Observability

| Layer | Where to look |
|---|---|
| Cloud Run request/response, stdout/stderr | Cloud Logging (`resource.type="cloud_run_revision"`) |
| Alert firing history | Cloud Monitoring → Alerting |
| Evaluation runs, retrieval metrics | MLflow UI (`MLFLOW_HOST`) — experiment per config |
| Drift reports (HTML) | GCS bucket + linked from MLflow runs |
| Airflow DAG history | Airflow UI (corpus refresh runs) |
| CI/CD history | GitHub Actions tab |

The backend writes structured JSON logs including query, retrieved chunk IDs, latency, and model version, so each production query is traceable end-to-end.

---

## 8. File-map (where everything lives)

```
terraform/                                # IaC for all GCP resources
  cloud_run.tf, cloud_sql.tf, monitoring.tf, iam.tf, artifact_registry.tf, …

.github/workflows/
  deploy.yml                              # build + deploy to Cloud Run
  eval_pipeline.yml                       # evaluate + register in Vertex AI
  drift_detection.yml                     # weekly composite drift check
  weekly_performance_check.yml            # weekly Evidently check
  corpus_refresh.yml                      # retraining pipeline + notifications
  ci.yml                                  # tests

backend/Dockerfile                        # python:3.11-slim, port 8000
ui/Dockerfile                             # node:20-alpine,   port 3000
docker-compose.yml                        # db + backend + frontend (local)

src/monitoring/
  drift_detection.py                      # composite drift
  performance_monitor.py                  # performance degradation
  build_reference_distribution.py         # reference embeddings
src/evaluation/
  retraining_thresholds.yaml              # 3 % / 30 % thresholds
  retrieval_model_configs.yaml            # model configs → Vertex AI
```

---

## 9. Mapping to the Submission Guidelines

| Guideline | Covered by |
|---|---|
| §2 Cloud vs. Edge (specify provider / service) | §1 above — GCP Cloud Run + Vertex AI |
| §3.1 Deployment Service | §2 — Cloud Run config, Vertex AI Model Registry |
| §3.2 Deployment Automation (Terraform / CI/CD) | §3 — `terraform/`, `deploy.yml`, `eval_pipeline.yml` |
| §3.3 Repo → Deployment connection | §4 — GitHub Actions on push / dispatch |
| §3.4 Replication steps | §5 — fresh-environment walkthrough |
| §5.1 Model decay / data shift monitoring | §6.1, §6.2 — Cloud Monitoring + MLflow + Evidently |
| §5.2 Data-shift detection | §6.2 — Evidently + centroid + per-dim p95 |
| §5.3 Retraining thresholds | §6.3 — `retraining_thresholds.yaml` |
| §5.4 Automated retraining pipeline | §6.4 — `corpus_refresh.yml` + regression gate |
| §5.5 Notifications | §6.5 — Slack + SMTP in `corpus_refresh.yml` |
| §6 Code submission (scripts, env config, logs) | §3, §7, §8 — workflows, Dockerfiles, compose, Terraform |
| §7 Video submission | Separate deliverable — fresh-env walkthrough following §5 |
