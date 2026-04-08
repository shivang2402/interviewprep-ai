# InterviewPrep-AI: Architecture Summary

## Overview

InterviewPrep-AI is an end-to-end data engineering pipeline that scrapes interview experiences from GeeksforGeeks, LeetCode, and Medium, processes raw data through a configurable multi-step transformation pipeline, validates output integrity, and loads cleaned documents into PostgreSQL. A full-stack web application (FastAPI backend + Next.js frontend) sits on top, exposing the data through a REST API with full-text and semantic search. The pipeline is orchestrated by Apache Airflow with artifacts stored in Google Cloud Storage (GCS).

---

## Architecture Layers

```
Scrapers (3 parallel)
  |
Raw documents --> GCS raw/{batch_id}/
  |
Preprocessing Pipeline (6 sequential steps)
  |
Processed documents --> GCS processed/{batch_id}/
  |
Validation (count matching, report existence)
  |
Database Loader --> PostgreSQL
  |
Chunking & Embeddings --> pgvector
  |
Email Notification

        --- Web Application Layer ---

PostgreSQL (pgvector)
  |
FastAPI Backend (REST API)
  |  - Documents: list, detail, chunks
  |  - Search: full-text (GIN index) + semantic (IVFFlat index)
  |  - Stats: overview, companies, topics, outcomes
  |  - Filters: dynamic options from real data
  |
Next.js Frontend (Browser)
     - Home: search bar, quick stats
     - Documents: filterable, paginated browse
     - Document Detail: content + metadata + chunks
     - Search: full-text / semantic toggle
     - Stats: companies, topics, outcomes dashboard
```

---

## File-by-File Breakdown

### 1. Data Models (`src/data_models/`)

| File | Purpose |
|------|---------|
| `scraped_document.py` | Frozen dataclass for raw, unprocessed documents emitted by scrapers. Fields include `document_id`, `source_platform`, `source_url`, `title`, `raw_content`, `published_at`, `scraped_at`, etc. Provides JSON serialization and stable document ID generation via SHA256 hashing of URLs. |
| `preprocessed_document.py` | Frozen dataclass for fully validated documents ready for DB insertion. Implements strict validation including required field checks, platform alias normalization (`geeksforgeeks` -> `gfg`), safe enum coercion, and interview type filtering. |
| `scraping_manifest.py` | Dataclass tracking scraper execution metadata: `scrape_date`, `scrape_type`, `started_at`, `completed_at`, `sources`, `total_files`, `last_sitemap_lastmod`. Uses `StorageBackend` abstraction for persistence. |
| `preprocessing_report.py` | Dataclass summarizing a full pipeline run. Tracks `batch_id`, timing, counts, per-step results, quarantined count, and status. Written to `processed/{batch_id}_report.json`. |
| `db_load_report.py` | Dataclass generated after DB insertion. Tracks total/inserted/skipped counts, lists of successful inserts, read errors, and insert errors. Stored at `gs://{bucket}/db-report/`. |
| `document_chunk.py` | Dataclass for document chunks used by the embedding pipeline. Stores chunk content, metadata (company, role, round, part info), and vector embeddings. |

---

### 2. Web Scrapers (`src/scrapers/`)

All scrapers follow a unified interface: accept a `StorageBackend`, produce `ScrapedInterviewDocument` objects, write manifests for state tracking. Batch IDs follow `{YYYY-MM-DD}_{bulk|weekly}` convention.

| File | Purpose |
|------|---------|
| `gfg.py` | **GeeksforGeeks scraper.** Sitemap-based strategy. Fetches sitemap index, filters to `post/` sitemaps, date-filters (bulk: `>= 2025-01-01`, incremental: last manifest watermark), extracts interview-experience URLs via regex, deduplicates against GCS before fetching. Parses pages with BeautifulSoup. Output: `raw/{batch_id}/gfg/`. |
| `leetcode.py` | **LeetCode scraper.** GraphQL API strategy. Queries `discussPostItems` with `tagSlugs: ["interview"]`, paginating in batches of 50. Fetches full content via `discussPostDetail`. Company extraction: post tags + title matching against 60+ companies. Handles rate limits (60s retry on 429). Output: `raw/{batch_id}/leetcode/`. |
| `medium.py` | **Medium scraper.** Playwright-based (client-side rendering). Launches headless Chromium with realistic fingerprint. Content extraction: primary via `__APOLLO_STATE__` JSON, fallback chain through `<article>` / `postArticle` / `<main>` tags. Paywall detection via multiple signals. Output: `raw/{batch_id}/medium/`. |
| `configs/gfg.py` | Static configuration for GFG scraper: URLs, regex patterns, batch ID generation, path construction. |
| `configs/leetcode.py` | Static configuration for LeetCode scraper: GraphQL queries (captured from browser DevTools), URLs, paths. |
| `configs/medium.py` | Static configuration for Medium scraper: sitemap URLs, browser settings, paths. |

---

### 3. Preprocessing Pipeline (`src/preprocessing/`)

Config-driven, single-process, checkpoint-based resilience. Raw docs flow through 6 sequential steps.

| File | Purpose |
|------|---------|
| `pipeline.py` | **Pipeline orchestrator.** Loads raw docs from GCS, builds step chain from `pipeline_config.yaml`, executes steps iteratively with checkpointing, handles resume-on-retry logic (checks Airflow `try_number`), splits valid docs from quarantined ones, writes final output to `processed/{batch_id}/`. |
| `steps/base.py` | Abstract `PreprocessingStep` class. Defines `name`, `process(doc)`, and `run_batch(docs)` with per-document error isolation, timing, and metrics aggregation. Returns `StepResult`. |
| `steps/content_normalizer.py` | **Step 1.** Normalizes HTML/Markdown to clean plain text. Pipeline: encoding fixes -> HTML stripping (BeautifulSoup) -> Markdown removal -> boilerplate removal -> emoji removal -> Unicode NFC normalization -> whitespace standardization. Filters: `empty_raw_content`, `empty_after_cleaning`. |
| `steps/pii_remover.py` | **Step 2.** Scrubs PII using regex patterns from `pii_patterns.yaml`. Replaces emails with `[EMAIL]`, phones with `[PHONE]`, URLs with `[PERSONAL_URL]`, etc. Never filters documents. |
| `steps/quality_filter.py` | **Step 3.** Drops low-quality docs. Checks (cheapest-first): word count bounds, error page detection, language detection (langdetect), interview signal ratio (2% threshold). Adds `quality_score` (0.0-1.0). |
| `steps/deduplicator.py` | **Step 4.** Two-tier dedup: (1) Exact via SHA256 hash (O(1) lookup), (2) Near via MinHash + LSH (0.80 similarity threshold, 128 permutations, 3-word shingles). State persists across batches. |
| `steps/entity_extractor.py` | **Step 5.** Extracts 8 structured fields via regex + curated dicts + spaCy NER (lazy-loaded). Fields: company, role, experience_level, interview_types, num_rounds, topics, outcome, difficulty. |
| `steps/schema_validator.py` | **Step 6.** Final gate. Maps enriched dict to `ProcessedInterviewDocument` constructor and validates. Filters: `schema_validation_failed`. |
| `registry.py` | Simple `Dict[str, type]` mapping step names to classes. Steps register via `steps/__init__.py`. |

#### Configuration Resources (`src/preprocessing/resources/`)

| File | Purpose |
|------|---------|
| `pipeline_config.yaml` | Master pipeline config: step ordering, checkpointing flags, batch sizes, GCS paths, fail_fast mode. |
| `normalization_patterns.yaml` | Regex patterns for text normalization. |
| `pii_patterns.yaml` | Regex patterns for PII detection (emails, phones, URLs, SSNs, etc.). |
| `quality_filters.yaml` | Thresholds for word count, language, signal ratio; error page patterns; interview keywords. |
| `dedup_configs.yaml` | Exact hash config, LSH similarity threshold, num_perm, shingle_size, state_dir. |
| `entity_extraction.yaml` | Regex patterns, company aliases, role aliases, keyword lists per topic category. |

---

### 4. Storage Layer (`src/storage/`)

| File | Purpose |
|------|---------|
| `storage_backend.py` | Abstract base class defining 4 methods: `write_json`, `read_json`, `file_exists`, `list_files`. Enables test/production swapping (in-memory dict for tests, GCS for production). |
| `gcs_backend.py` | GCS implementation. Auth priority: (1) Secret Manager, (2) Default credentials. Handles JSON read/write, blob listing (sorted newest-first), bucket existence verification. |

---

### 5. Database Layer (`src/database/`)

| File | Purpose |
|------|---------|
| `loader.py` | **Batch DB loader.** Reads processed JSON from GCS in configurable chunks (default 50), deserializes into `ProcessedInterviewDocument`, performs idempotent upserts via `ON CONFLICT DO UPDATE` into `processed_documents` and `interview_metadata` tables. Get-or-create for company/role lookups with in-memory caching. Per-row error isolation. |
| `queries.py` | SQL query constants: `UPSERT_PROCESSED_DOC` and `UPSERT_INTERVIEW_META` with enum casts, JSONB, and `text[]` array handling. |
| `sanitizers.py` | Maps Python model values to valid PostgreSQL enum values. Converts `"unknown"` to `NULL`, handles platform alias mapping. |

---

### 6. Chunking & Embeddings (`src/chunking/` & `src/embeddings/`)

| File | Purpose |
|------|---------|
| `chunking/chunker.py` | Splits documents into semantic chunks for embedding/retrieval. Detects interview round boundaries via regex. Generates `DocumentChunk` objects with context headers (company, role, round, part). |
| `chunking/chunking_config.yaml` | Chunk size in words, overlap, min doc words, round boundary patterns. |
| `embeddings/pipeline.py` | Generates vector embeddings for document chunks. Configurable biencoder models (e.g., `all-MiniLM-L6-v2`, `all-mpnet-base-v2`). Updates embedding columns in `document_chunks` table via `pgvector`. Writes manifest to GCS. |
| `embeddings/embeddings_configs.yaml` | Model list, batch sizes for embedding generation. |

---

### 7. Orchestration (`dags/`)

| File | Purpose |
|------|---------|
| `scraping_pipeline.py` | **Airflow DAG** (`interview_scraping_pipeline`). Manual trigger, no schedule. Task flow: `start` -> 3 parallel scrapers -> `print_summary` -> `run_preprocessing` -> `validate_processed_data` -> `load_to_database` -> `complete` -> `build_email` -> `send_notification_email`. Supports demo mode via `dag_run.conf`. Email sends on all outcomes (`trigger_rule='all_done'`). |

---

### 8. Tests (`test/`)

Framework: pytest with unittest.mock (no real GCS, DB, or network calls).

| Directory/File | Purpose |
|----------------|---------|
| `test/database/conftest.py` | Shared DB test fixtures. |
| `test/database/test_loader.py` | BatchDBLoader tests: mocks GCS + psycopg2, verifies SQL execution, error isolation, summary generation. |
| `test/database/test_report.py` | Report schema validation tests. |
| `test/database/test_sanitizers.py` | Sanitizer mapping tests. |
| `test/preprocessing/conftest.py` | Shared preprocessing fixtures. |
| `test/preprocessing/test_pipeline.py` | Pipeline orchestrator tests: CheckpointManager, step building, resume logic, quarantine splitting. |
| `test/preprocessing/test_pipeline_integration.py` | End-to-end preprocessing integration tests. |
| `test/preprocessing/steps/test_base.py` | Base step class tests. |
| `test/preprocessing/steps/test_content_normalizer.py` | Content normalizer step tests. |
| `test/preprocessing/steps/test_deduplicator.py` | Deduplicator step tests. |
| `test/preprocessing/steps/test_entity_extractor.py` | Entity extractor step tests. |
| `test/preprocessing/steps/test_pii_remover.py` | PII remover step tests. |
| `test/preprocessing/steps/test_quality_filter.py` | Quality filter step tests. |
| `test/preprocessing/steps/test_schema_validator.py` | Schema validator step tests. |
| `test/scrapers/configs/test_gfg.py` | GFG config attribute/pattern tests. |
| `test/scrapers/configs/test_leetcode.py` | LeetCode config tests. |
| `test/scrapers/configs/test_medium.py` | Medium config tests. |
| `test/scrapers/test_gfg.py` | GFG scraper tests: mocked HTTP, sitemap parsing. |
| `test/scrapers/test_leetcode.py` | LeetCode scraper tests: mocked GraphQL. |
| `test/scrapers/test_medium.py` | Medium scraper tests: mocked Playwright. |
| `test/storage/test_gcs_backend.py` | GCS backend tests: all auth paths, CRUD operations. |
| `test/storage/test_storage_backend.py` | Storage backend interface tests. |
| `test/test_dag.py` | DAG structure validation (task dependencies, operator types). |

---

### 9. CI/CD (`.github/workflows/`)

| File | Purpose |
|------|---------|
| `ci.yml` | GitHub Actions workflow. Runs on push to main and PRs. Python 3.10, installs deps + Airflow + spaCy model + sentence-transformers. Runs pytest with 80% coverage threshold. Uploads test results + HTML reports as artifacts. |

---

### 10. Root Configuration Files

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies: requests, beautifulsoup4, google-cloud-storage, playwright, markdownify, pyyaml, langdetect, datasketch, spacy, psycopg2-binary, pytest, sentence-transformers. |
| `requirements-test.txt` | Test-specific dependencies. |
| `readme.md` | Project documentation with setup instructions and architecture overview. |

---

### 11. Backend API (`backend/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app entrypoint. CORS middleware (configurable origins), global exception handler, health check endpoint. Calls `create_indexes()` on startup to ensure GIN and IVFFlat indexes exist. |
| `db/connection.py` | Database connection pool (psycopg2 `SimpleConnectionPool`). Supports two modes via `DB_CONNECTION_MODE`: `tcp` (local dev via Cloud SQL Auth Proxy) and `socket` (Cloud Run via Unix socket). Optionally pulls credentials from GCP Secret Manager. Exposes `get_connection()` context manager. |
| `db/queries.py` | All SQL query constants. Document list/detail with JOINs across `processed_documents`, `interview_metadata`, `companies`, `roles`. Full-text search using `to_tsvector`/`plainto_tsquery` with `coalesce()` to match the GIN index. Semantic search using pgvector cosine distance (`<=>`). Stats aggregations and filter option queries. |
| `db/create_indexes.py` | One-time index creation script run on startup. Creates `idx_fts_documents` (GIN on tsvector) and `idx_embedding_minilm` (IVFFlat on vector embeddings with 100 lists). Uses `CREATE INDEX IF NOT EXISTS` for idempotency. |
| `routers/documents.py` | `GET /api/documents` (paginated, filterable by platform/company/role/outcome/difficulty), `GET /api/documents/{id}` (full detail), `GET /api/documents/{id}/chunks` (text chunks). Dynamic WHERE clause building with parameterized queries. |
| `routers/search.py` | `GET /api/search?q=...` (full-text with pagination), `GET /api/search/semantic?q=...` (vector similarity). Semantic search lazy-loads `sentence-transformers` model, encodes query, queries pgvector. Both support platform/company/difficulty filters. |
| `routers/stats.py` | `GET /api/stats/overview`, `/stats/companies`, `/stats/topics`, `/stats/outcomes`. `GET /api/filters/options` returns all valid filter values for UI dropdowns. |
| `models/schemas.py` | Pydantic response models: `DocumentSummary`, `DocumentDetail`, `DocumentChunk`, `SearchResult`, `SemanticSearchResult`, `StatsOverview`, `CompanyStat`, `TopicStat`, `OutcomeStat`, `FilterOptions`. |

---

### 12. Frontend UI (`ui/`)

| File | Purpose |
|------|---------|
| `lib/types.ts` | TypeScript interfaces matching all backend response schemas. |
| `lib/api.ts` | Typed API client using `fetch`. All calls go to `NEXT_PUBLIC_API_BASE_URL`. Functions for documents, search, semantic search, stats, and filter options. |
| `app/page.tsx` | Home page. Search bar (navigates to `/search`), quick stats bar (total documents, companies, platforms), project description, links to Documents and Stats. |
| `app/documents/page.tsx` | Document list page. Fetches filter options on mount, renders `FilterBar` (5 dropdowns), paginated grid of `DocumentCard` components. |
| `app/documents/[id]/page.tsx` | Document detail page. Fetches document + chunks in parallel. Shows `DocumentDetailView` with all metadata and content. Collapsible chunks section. |
| `app/search/page.tsx` | Search page. `SearchBar` with full-text/semantic radio toggle. Filter dropdowns for platform, company, difficulty. Renders `FulltextResults` or `SemanticResults` based on mode. Paginated for full-text. |
| `app/stats/page.tsx` | Stats dashboard. Fetches all four stats endpoints in parallel. `StatCard` grid for overview, `CompanyTable` for top 25, `TopicsChart` with percentage bars, `OutcomeChart` with distribution bars. |
| `components/layout/Header.tsx` | Site header with nav links (Home, Documents, Search, Stats). Active link highlighting via `usePathname`. |
| `components/layout/Footer.tsx` | Site footer with project tagline. |
| `components/documents/DocumentCard.tsx` | Card showing title, platform badge, company, role, difficulty, outcome, date. Links to detail page. |
| `components/documents/DocumentDetail.tsx` | Full document view: metadata grid, topics tags, cleaned content block. |
| `components/documents/FilterBar.tsx` | Five select dropdowns populated from `FilterOptions`. Calls `onChange` on selection. |
| `components/documents/Pagination.tsx` | Previous/Next buttons with page count. |
| `components/search/SearchBar.tsx` | Text input with submit button and full-text/semantic radio toggle. |
| `components/search/SearchResults.tsx` | `FulltextResults`: cards with snippet (HTML rendered). `SemanticResults`: cards with similarity percentage and raw text preview. |
| `components/stats/StatCard.tsx` | Single metric card with label and formatted number. |
| `components/stats/CompanyTable.tsx` | Table with company name and document count columns. |
| `components/stats/TopicsChart.tsx` | Horizontal bar chart (CSS-based) showing top 20 topics by frequency. |
| `components/stats/OutcomeChart.tsx` | Percentage bars for each interview outcome. |

---

## GCS Data Layout

```
gs://interviewprep-ai-data/
  raw/{batch_id}/gfg/          # Raw scraped documents
  raw/{batch_id}/leetcode/
  raw/{batch_id}/medium/
  manifests/{batch_id}/        # Scraping & preprocessing manifests
  processed/{batch_id}/        # Cleaned, validated documents
  quarantine/{batch_id}/       # Failed validation (for manual review)
  checkpoints/{batch_id}/      # Intermediate pipeline state
  db-report/                   # Database load reports
```

---

## Key Design Patterns

1. **StorageBackend abstraction** - All I/O goes through an interface, enabling test/prod swapping
2. **Config-driven pipeline** - Step ordering, thresholds, and toggles live in YAML
3. **Per-document error isolation** - One bad document never blocks the batch
4. **Checkpoint-based resilience** - Expensive steps checkpoint to GCS; on retry, resumes from last checkpoint
5. **Quarantine pattern** - Failed documents written to separate path for manual review, not silently dropped
6. **Idempotent upserts** - `ON CONFLICT DO UPDATE` makes DB writes safe to re-run
7. **Two-tier deduplication** - Exact hashes (O(1)) + MinHash LSH (catches paraphrased reposts)
8. **Lazy model loading** - spaCy NER model loaded on first use, not at import time
9. **Parallel scraping + sequential preprocessing** - Scrapers fan out; preprocessing runs single-process with checkpoints
10. **Email on all outcomes** - Notification sends regardless of pipeline success/failure

---

## External Services

- **Google Cloud Storage** - Data storage (raw, processed, checkpoints, quarantine, reports)
- **PostgreSQL (Cloud SQL)** - `processed_documents`, `interview_metadata`, `companies`, `roles`, `document_chunks` tables
- **Apache Airflow** - DAG orchestration, task scheduling, XCom passing
- **spaCy** - NER model (`en_core_web_sm`) for entity recognition
- **sentence-transformers** - Biencoder models for vector embeddings
- **pgvector** - PostgreSQL extension for vector similarity search
