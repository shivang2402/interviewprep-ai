# How to Run InterviewPrep-AI

## 1. Prerequisites

- Python 3.10+
- Google Cloud SDK (for GCS authentication)
- PostgreSQL client libraries (for `psycopg2`)

---

## 2. Python Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP client for GFG and LeetCode scrapers |
| `beautifulsoup4` | HTML parsing for GFG scraper and Medium content extraction |
| `google-cloud-storage` | GCS backend for all storage operations |
| `playwright` | Headless browser automation for Medium scraper |
| `markdownify` | HTML-to-Markdown conversion for Medium content |
| `pyyaml` | YAML config loading for preprocessing steps and pipeline |
| `langdetect` | Language detection in QualityFilter step |
| `datasketch` | MinHash + LSH for near-duplicate detection |
| `spacy` | NER-based company extraction in EntityExtractor |
| `psycopg2-binary` | PostgreSQL driver for the database loader |
| `sentence-transformers` | Bi-encoder embedding models for chunking and retrieval |
| `numpy` | Array operations for embeddings and metric computation |
| `pandas` | Tabular data handling for eval dataset labelling |
| `pgvector` | PostgreSQL vector similarity search extension |
| `rank-bm25` | BM25 scoring for lexical retrieval in eval dataset generation |
| `openai` | LLM-as-a-judge relevance grading for eval dataset |
| `mlflow` | Experiment tracking for retrieval model evaluation |
| `pytest` | Test framework |

---

## 3. Environment Setup

```bash
# 1. Clone the repository
git clone <repo-url> && cd interviewprep-ai

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Download spaCy English model (used by EntityExtractor)
python -m spacy download en_core_web_sm

# 5. Install Playwright browsers (used by MediumScraper)
playwright install chromium

# 6. Set environment variables
export GCS_BUCKET_NAME="interviewprep-ai-data"
export GCP_PROJECT_ID="professorbot-dovbsg"
export DB_HOST="34.148.0.165"
export DB_NAME="interviewprep-ai-database"
export DB_USER="postgres"
export DB_PASSWORD="<your-password>"
export DB_PORT="5432"

# 7. Authenticate with GCP (choose one)
# Option A: Application Default Credentials (local dev)
gcloud auth application-default login
# Option B: Service account key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"

# 8. Initialize Airflow (if running locally)
export AIRFLOW_HOME=~/airflow
airflow db init
cp dags/scraping_pipeline.py $AIRFLOW_HOME/dags/
cp dags/chunking_embedding_pipeline.py $AIRFLOW_HOME/dags/

# 9. Set MLflow tracking URI (for evaluation pipeline)
export MLFLOW_TRACKING_URI="http://<mlflow-host>:5000"

# 10. Run tests to verify setup
pytest test/ -v
```

---

## 4. Reproducibility

### Reproducing the Pipeline from Scratch

```bash
# 1. Clone and set up the environment (see above)
git clone <repo-url> && cd interviewprep-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
playwright install chromium

# 2. Configure GCP credentials and environment variables
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
export DB_HOST="..." DB_NAME="..." DB_USER="..." DB_PASSWORD="..." DB_PORT="5432"

# 3. Verify tests pass
pytest test/ -v

# 4. Initialize Airflow
export AIRFLOW_HOME=~/airflow
airflow db init
cp dags/scraping_pipeline.py $AIRFLOW_HOME/dags/
cp dags/chunking_embedding_pipeline.py $AIRFLOW_HOME/dags/

# 5. Trigger the data pipeline
airflow dags trigger interview_scraping_pipeline

# 6. Trigger the chunking + embedding pipeline
airflow dags trigger chunking_embedding_pipeline

# 7. Run retrieval evaluation (requires MLflow + DB access)
export MLFLOW_TRACKING_URI="http://<mlflow-host>:5000"
python src/evaluation/evaluator.py
```

### What Makes It Reproducible

- **Idempotent DB writes** — `ON CONFLICT DO UPDATE` means you can re-run the pipeline on the same batch without duplicating data.
- **Batch ID determinism** — The batch ID is derived from Airflow's `logical_date`, so the same trigger date always produces the same batch ID and GCS paths.
- **Checkpoint recovery** — Preprocessing saves intermediate state to GCS. On retry, it resumes from the last checkpoint rather than re-processing from scratch.
- **Dedup before fetch** — Scrapers check GCS before downloading, so re-running a scrape on the same batch skips already-collected documents.
- **Config-driven pipeline** — Step ordering, thresholds, and toggle switches live in YAML configs, not code. Changing the pipeline behavior doesn't require code changes.
- **Pinned dependencies** — `requirements.txt` locks the dependency set. For full reproducibility, consider generating a `pip freeze` snapshot.
- **Manifest watermarks** — Each scraping run writes a manifest with `last_sitemap_lastmod`, enabling incremental runs that pick up exactly where the last run left off.

---

## 5. Test Suite

### Overview

The project has a comprehensive test suite with **29 test files** across 9 modules, plus 2 shared `conftest.py` fixture files. Everything uses `pytest` with `unittest.mock` — no real GCS, database, or network calls needed to run the tests. Tests with missing optional dependencies (e.g., `sentence_transformers`, `mlflow`, `airflow`) skip gracefully via `pytest.importorskip`.

### What's Covered

- **Preprocessing steps** — Each of the 6 steps has its own test file covering happy paths, filtering behavior, edge cases, and `run_batch()` integration. The deduplicator tests include state persistence and MinHash accuracy. The schema validator tests use parametrized fixtures for required field validation.
- **Pipeline orchestrator** — Tests for `CheckpointManager` (save/load/cleanup), `_build_steps()` (enabled/disabled/unknown), `_resolve_start()` (fresh vs resume), quarantine splitting, and full `run()` flows (success, resume, fail_fast, exception handling).
- **Database** — Loader tests mock both GCS and psycopg2, verifying correct SQL execution, error isolation, and summary generation. Sanitizer tests cover all enum mappings.
- **Scrapers** — Config tests validate static attributes, URL patterns, and path generation. Implementation tests mock HTTP/GraphQL/Playwright calls and verify parsing, dedup, error handling, and manifest creation.
- **Storage** — GCS backend tests cover all auth paths, CRUD operations, and temp key cleanup. The ABC test verifies that partial implementations are rejected.
- **Chunking** — Tests for word counting, sentence splitting, header building, strategy detection, chunk_document, validate_chunks, DB fetch/insert, GCS manifest writing, and pipeline run flow.
- **Embeddings** — Tests for column naming, missing embeddings fetch, batch update, manifest writing, and pipeline run.
- **Eval dataset labelling** — Tests for score normalization, hybrid fusion, BM25 index, result pooling, chunk truncation, LLM response parsing, retry logic, CSV reading, and DB insertion.
- **Evaluation** — Tests for retrieval metrics (MRR, Recall, Precision, NDCG), retrieval strategies, RRF fusion, bias report, config loading, selection score, and decision gate.
- **DAGs** — Tests for task helper functions (`_as_bool`, `_as_int`, `_safe_variable_get`) and task callables with demo mode patching.

### Running Tests

```bash
# Run everything
pytest test/ -v

# Run a specific module
pytest test/preprocessing/ -v
pytest test/database/ -v
pytest test/scrapers/ -v
pytest test/storage/ -v
pytest test/chunking/ -v
pytest test/embeddings/ -v
pytest test/eval_dataset_labelling/ -v
pytest test/evaluation/ -v

# Run with coverage
pytest test/ --cov=src --cov-report=term-missing

# Run tests matching a pattern
pytest test/ -k "test_exact_duplicate" -v
```

---

## 6. Local Development with Docker Compose

If you don't want to set up PostgreSQL and all dependencies locally, use Docker Compose. It spins up the full stack: PostgreSQL (with pgvector), the FastAPI backend, and the Next.js frontend.

```bash
# 1. Set your OpenAI key
export OPENAI_API_KEY="sk-..."

# 2. Start all services
docker compose up --build

# 3. Access the app
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs
# PostgreSQL: localhost:5432 (user: postgres, password: admin)

# 4. Stop everything
docker compose down

# 5. Stop and wipe the database volume
docker compose down -v
```

The backend connects to the local PostgreSQL container, not Cloud SQL. The `sentence-transformers` model is pre-baked into the Docker image so there's no download at startup.

---

## 7. Deploying to GCP (Cloud Run)

### Prerequisites

- GCP project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth login`)
- Docker with buildx support
- APIs enabled: Cloud Run, Artifact Registry, Cloud SQL, Secret Manager

### Step 1: Build and push images

```bash
# Authenticate Docker to Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build backend (from repo root)
docker buildx build --platform linux/amd64 \
  -f backend/Dockerfile \
  -t us-central1-docker.pkg.dev/professorbot-dovbsg/interviewprep-ai/backend:latest \
  --push .

# Build frontend (pass backend URL as build arg — NEXT_PUBLIC_* vars are baked at build time)
docker buildx build --platform linux/amd64 \
  -f ui/Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://<BACKEND_CLOUD_RUN_URL> \
  -t us-central1-docker.pkg.dev/professorbot-dovbsg/interviewprep-ai/frontend:latest \
  --push ui/
```

**Important:** `NEXT_PUBLIC_API_BASE_URL` must be set at **build time** because Next.js inlines it into the client JavaScript bundle. Setting it as a Cloud Run runtime env var has no effect on browser-side code.

### Step 2: Deploy backend

```bash
gcloud run deploy interviewprep-backend \
  --image us-central1-docker.pkg.dev/professorbot-dovbsg/interviewprep-ai/backend:latest \
  --region us-central1 \
  --add-cloudsql-instances professorbot-dovbsg:us-central1:interviewprep-ai-db \
  --set-env-vars "DB_CONNECTION_MODE=socket,\
    CLOUD_SQL_INSTANCE_CONNECTION_NAME=professorbot-dovbsg:us-central1:interviewprep-ai-db,\
    DB_NAME=interviewprep-ai-database,\
    DB_USER=postgres,\
    DB_PASSWORD=<your-password>,\
    OPENAI_API_KEY=<your-key>,\
    EMBEDDING_MODEL=all-MiniLM-L6-v2,\
    ALLOWED_ORIGINS=https://<FRONTEND_CLOUD_RUN_URL>" \
  --memory 2Gi --cpu 2 \
  --min-instances 1 --max-instances 10 \
  --port 8000 --allow-unauthenticated
```

### Step 3: Deploy frontend

```bash
gcloud run deploy interviewprep-frontend \
  --image us-central1-docker.pkg.dev/professorbot-dovbsg/interviewprep-ai/frontend:latest \
  --region us-central1 \
  --memory 512Mi --cpu 1 \
  --min-instances 0 --max-instances 5 \
  --port 3000 --allow-unauthenticated
```

### Step 4: Verify

```bash
# Backend health
curl https://<BACKEND_URL>/api/health

# Should return: {"status":"ok","rag_ready":true,...}
```

### CI/CD (Automated)

Push to `main` triggers `.github/workflows/deploy.yml` which builds, pushes, and deploys both services automatically. Required GitHub Secrets:

| Secret | Value |
|--------|-------|
| `GCP_SA_KEY` | Service account JSON key |
| `CLOUD_SQL_INSTANCE` | `professorbot-dovbsg:us-central1:interviewprep-ai-db` |
| `DB_NAME` | `interviewprep-ai-database` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | Database password |
| `OPENAI_API_KEY` | OpenAI API key |
| `BACKEND_SERVICE_URL` | Backend Cloud Run URL |
| `FRONTEND_SERVICE_URL` | Frontend Cloud Run URL |
| `MLFLOW_TRACKING_URI` | MLflow server URL |
| `BACKEND_SA_EMAIL` | Backend service account email |

---

## 8. Infrastructure as Code (Terraform)

All GCP resources can be provisioned via Terraform in `terraform/`.

```bash
cd terraform

# Copy and fill in variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Initialize and apply
terraform init
terraform plan
terraform apply
```

This creates: Cloud Run services, Cloud SQL instance, Artifact Registry, service accounts, IAM bindings, Secret Manager secrets, and monitoring alerts.