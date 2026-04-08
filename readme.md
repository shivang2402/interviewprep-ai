# InterviewPrep-AI

## Full Stack Application

InterviewPrep-AI includes a full-stack web application on top of the data pipeline:

- **Backend** (`backend/`): A FastAPI REST API that exposes the processed interview data from PostgreSQL. Supports paginated document browsing, full-text search, semantic search (via pgvector embeddings), and statistics aggregation. See [backend/README.md](backend/README.md) for setup and endpoint documentation.

- **Frontend** (`ui/`): A Next.js 14 (TypeScript + Tailwind CSS) application that provides a clean interface for browsing documents, searching with full-text or semantic modes, and viewing pipeline statistics. See [ui/README.md](ui/README.md) for setup instructions.

The frontend communicates exclusively with the backend API. The backend reads from the same PostgreSQL database populated by the data pipeline. No data flows directly from the UI to the database.

---

## 1. Project Overview

InterviewPrep-AI is an end-to-end data engineering pipeline that scrapes interview experiences from three major platforms — **GeeksforGeeks**, **LeetCode**, and **Medium** — preprocesses the raw data through a multi-step transformation pipeline, validates output integrity, and loads the cleaned documents into a PostgreSQL database. The whole thing is orchestrated by **Apache Airflow**, with raw and processed artifacts stored in **Google Cloud Storage (GCS)**. After every run, the team gets an email report with the full pipeline status.

---

## 2. Folder Structure

The repository is structured to separate orchestration, core logic (`src`), testing, and configuration. 

```text
interviewprep-ai/
├── .venv/                              # Python virtual environment
├── dags/                               # Airflow DAGs directory
│   └── scraping_pipeline.py            # Main orchestration DAG for the pipeline
├── src/                                # Main source code directory
│   ├── data_models/                    # Data schemas and Pydantic/dataclass models
│   │   ├── __init__.py                 # Package initialization
│   │   ├── db_load_report.py           # Model representing the database load summary report
│   │   ├── preprocessed_document.py    # Schema for cleaned and transformed documents
│   │   ├── preprocessing_report.py     # Model tracking preprocessing success/failure stats
│   │   ├── scraped_document.py         # Schema for raw documents parsed by scrapers
│   │   └── scraping_manifest.py        # Model tracking scraper execution runs and state
│   ├── database/                       # Database interaction layer
│   │   ├── __init__.py                 # Package initialization
│   │   ├── loader.py                   # Handles bulk inserts of processed data to PostgreSQL
│   │   ├── queries.py                  # SQL query definitions
│   │   └── sanitizers.py               # SQL injection prevention and data sanitation utils
│   ├── preprocessing/                  # Data transformation and cleaning pipeline
│   │   ├── resources/                  # Preprocessing YAML assets
│   │   │   ├── dedup_configs.yaml      # Deduplication logic configuration
│   │   │   ├── entity_extraction.yaml  # Configs for NER extraction
│   │   │   ├── normalization_patterns.yaml # Regex patterns for text normalization
│   │   │   ├── pii_patterns.yaml       # Regex patterns for removing Personally Identifiable Information
│   │   │   ├── pipeline_config.yaml    # Master config ordering the pipeline steps
│   │   │   └── quality_filters.yaml    # Thresholds for quarantine/filtering documents
│   │   ├── steps/                      # Individual transformation steps (the 6-step pipeline)
│   │   │   ├── __init__.py             # Package initialization
│   │   │   ├── base.py                 # Base class interface for all steps
│   │   │   ├── content_normalizer.py   # Step: Normalizes text and markdown formats
│   │   │   ├── deduplicator.py         # Step: Removes duplicate entries
│   │   │   ├── entity_extractor.py     # Step: Extracts companies, roles, and skills
│   │   │   ├── pii_remover.py          # Step: Scrubs personal data (names, emails)
│   │   │   ├── quality_filter.py       # Step: Quarantines low-quality/stub documents
│   │   │   └── schema_validator.py     # Step: Validates final output against Pydantic schema
│   │   ├── __init__.py                 # Package initialization
│   │   ├── pipeline.py                 # Orchestrator chaining the preprocessing steps
│   │   └── registry.py                 # Registration logic for dynamically loading steps
│   ├── scrapers/                       # Web scraping modules
│   │   ├── configs/                    # Scraper-specific configuration files
│   │   │   ├── __init__.py             # Package initialization
│   │   │   ├── gfg.py                  # GeeksforGeeks scraper config
│   │   │   ├── leetcode.py             # LeetCode scraper config
│   │   │   └── medium.py               # Medium scraper config
│   │   ├── logs/                       # Log output directory for scraper executions
│   │   │   └── __init__.py             # Directory initialization
│   │   ├── __init__.py                 # Package initialization
│   │   ├── gfg.py                      # GeeksforGeeks scraper implementation
│   │   ├── leetcode.py                 # LeetCode scraper implementation
│   │   └── medium.py                   # Medium scraper implementation
│   └── storage/                        # Cloud and local storage integrations
│       ├── __init__.py                 # Package initialization
│       ├── gcs_backend.py              # Google Cloud Storage adapter
│       └── storage_backend.py          # Abstract base class/interface for storage operations
├── test/                               # Unit and integration test suite
│   ├── database/                       # Database tests
│   │   ├── conftest.py                 # Pytest fixtures for DB tests
│   │   ├── test_loader.py              # Tests for DB loader logic
│   │   ├── test_report.py              # Tests for DB reporting schemas
│   │   └── test_sanitizers.py          # Tests for SQL sanitizer functions
│   ├── preprocessing/                  # Preprocessing tests
│   │   ├── steps/                      # Tests for individual steps
│   │   │   ├── __init__.py             # Package initialization
│   │   │   ├── test_base.py            # Tests for step base class
│   │   │   ├── test_content_normalizer.py # Tests text normalization logic
│   │   │   ├── test_deduplicator.py    # Tests deduplication detection
│   │   │   ├── test_entity_extractor.py# Tests entity extraction accuracy
│   │   │   ├── test_pii_remover.py     # Tests PII redaction logic
│   │   │   ├── test_quality_filter.py  # Tests quarantine thresholds
│   │   │   └── test_schema_validator.py# Tests final output validation
│   │   ├── __init__.py                 # Package initialization
│   │   ├── conftest.py                 # Pytest fixtures for preprocessing
│   │   └── test_pipeline.py            # Integration tests for full pipeline execution
│   ├── scrapers/                       # Scraper tests
│   │   ├── configs/                    # Scraper config tests
│   │   │   ├── __init__.py             # Package initialization
│   │   │   ├── test_gfg.py             # Config tests for GFG
│   │   │   ├── test_leetcode.py        # Config tests for Leetcode
│   │   │   └── test_medium.py          # Config tests for Medium
│   │   ├── __init__.py                 # Package initialization
│   │   ├── test_gfg.py                 # GFG scraper parsing/network tests
│   │   ├── test_leetcode.py            # LeetCode scraper parsing/network tests
│   │   └── test_medium.py              # Medium scraper parsing/network tests
│   └── storage/                        # Storage layer tests
│       ├── __init__.py                 # Package initialization
│       ├── test_gcs_backend.py         # Tests for GCS reading/writing
│       └── test_storage_backend.py     # Tests for abstract storage classes
├── .gitignore                          # Git ignore definitions
├── readme.md                           # Project documentation
└── requirements.txt                    # Python dependencies
```

---

## Wrap-up

This project brings together web scraping, NLP preprocessing, and structured data loading into a single Airflow-orchestrated pipeline. For setup instructions and how to run tests, see [`useme.md`](useme.md). For detailed pipeline architecture, see [`data-pipeline-readme.md`](docs/data-pipeline-readme.md).

---

## Full Architecture

### Data Pipeline

The pipeline runs as an Airflow DAG. Three scrapers (GeeksforGeeks, LeetCode, Medium) run in parallel, writing raw documents to GCS. The preprocessing pipeline then processes these documents through six sequential steps: content normalization, PII removal, quality filtering, deduplication (exact + near-duplicate via MinHash LSH), entity extraction (company, role, topics via regex and spaCy NER), and schema validation. Valid documents are written to GCS and loaded into PostgreSQL via idempotent upserts. Failed documents are quarantined for review. The pipeline supports checkpoint-based resume on retry.

### Embedding Pipeline

After documents are loaded, the chunking pipeline splits them into semantic chunks based on interview round boundaries (or fixed windows for unstructured content). Each chunk gets a context header prepended (company, role, round). The embedding pipeline then generates vector embeddings using sentence-transformer models (all-MiniLM-L6-v2 at 384 dimensions, all-mpnet-base-v2 at 768 dimensions) and stores them in PostgreSQL via the pgvector extension.

### Backend API

The FastAPI backend sits between the database and the frontend. It exposes endpoints for paginated document listing with filters, document detail and chunk retrieval, full-text search (using PostgreSQL's tsvector/tsquery), semantic search (encoding the query with the same sentence-transformer model and using pgvector cosine distance), and statistics aggregation. The backend supports two database connection modes: TCP (for local development via Cloud SQL Auth Proxy) and Unix socket (for Cloud Run deployment).

### Frontend

The Next.js frontend consumes the backend API. It provides a home page with search and overview stats, a filterable document browser, document detail views with collapsible chunks, a search page with toggle between full-text and semantic modes, and a statistics dashboard showing company rankings, topic frequencies, and outcome distributions. All filter options are populated dynamically from the database via the API.

### How Semantic Search Works

1. The data pipeline chunks documents and generates embeddings using sentence-transformers
2. Embeddings are stored in the `document_chunks` table using pgvector's `vector` type
3. When a user submits a semantic search query, the backend encodes the query string using the same model
4. The backend queries pgvector using cosine distance (`<=>` operator) to find the most similar chunks
5. Results are returned with similarity scores and displayed in the UI

### Architecture Diagram

```
                        +------------------+
                        |   Apache Airflow |
                        +--------+---------+
                                 |
              +------------------+------------------+
              |                  |                  |
        +-----+------+   +------+-----+   +-------+----+
        | GFG Scraper|   | LC Scraper |   | Med Scraper|
        +-----+------+   +------+-----+   +-------+----+
              |                  |                  |
              +------------------+------------------+
                                 |
                         +-------+--------+
                         | GCS (Raw Data) |
                         +-------+--------+
                                 |
                    +------------+-------------+
                    | Preprocessing Pipeline   |
                    | (6 steps, checkpointed)  |
                    +------------+-------------+
                                 |
                    +------------+-------------+
                    | GCS (Processed + Reports)|
                    +------------+-------------+
                                 |
                    +------------+-------------+
                    | PostgreSQL (Cloud SQL)    |
                    | - processed_documents    |
                    | - interview_metadata     |
                    | - companies / roles      |
                    +------------+-------------+
                                 |
                    +------------+-------------+
                    | Chunking + Embeddings    |
                    | (sentence-transformers)  |
                    +------------+-------------+
                                 |
                    +------------+-------------+
                    | document_chunks + pgvec  |
                    +------------+-------------+
                                 |
                    +------------+-------------+
                    | FastAPI Backend          |
                    | (REST API)              |
                    +------------+-------------+
                                 |
                    +------------+-------------+
                    | Next.js Frontend         |
                    | (Browser)               |
                    +----------------------------+
```