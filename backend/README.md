# InterviewPrep AI — Backend

A FastAPI application that exposes the interview experience data from the InterviewPrep AI pipeline via a REST API. It reads from the existing PostgreSQL database populated by the data pipeline and supports full-text search, vector similarity search (via pgvector), and statistics aggregation.

## Project Structure

```
backend/
  main.py               # FastAPI app entrypoint, CORS config, error handling
  routers/
    documents.py         # Document list, detail, and chunks endpoints
    search.py            # Full-text and semantic search endpoints
    stats.py             # Statistics and filter options endpoints
  db/
    connection.py        # Database connection pool with TCP/socket mode support
    queries.py           # SQL query definitions
  models/
    schemas.py           # Pydantic response models
  .env.example           # Environment variable template
  requirements.txt       # Python dependencies
```

## Endpoints

### Documents

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/documents` | Paginated list. Params: `page`, `limit`, `platform`, `company`, `role`, `outcome`, `difficulty` |
| GET | `/api/documents/{document_id}` | Full document detail with metadata |
| GET | `/api/documents/{document_id}/chunks` | Text chunks for a document |

### Search

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/search?q=...` | Full-text search. Params: `q`, `page`, `limit`, `platform`, `company`, `difficulty` |
| GET | `/api/search/semantic?q=...` | Vector similarity search via pgvector. Params: `q`, `limit`, `platform`, `company`, `difficulty` |

### Stats

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stats/overview` | Total documents, companies, roles, platform breakdown |
| GET | `/api/stats/companies` | Companies ranked by document count |
| GET | `/api/stats/topics` | Topics ranked by frequency |
| GET | `/api/stats/outcomes` | Interview outcome distribution |

### Meta

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (`{"status": "ok"}`) |
| GET | `/api/filters/options` | All valid filter values for UI dropdowns |

### Response Format

All endpoints return a consistent envelope:

```json
{
  "data": "...",
  "meta": {
    "total": 100,
    "page": 1,
    "limit": 20
  }
}
```

## Local Setup

1. Install dependencies:
   ```
   cd backend
   pip install -r requirements.txt
   ```

2. Start Cloud SQL Auth Proxy (for local TCP connection to Cloud SQL):
   ```
   cloud-sql-proxy INSTANCE_CONNECTION_NAME --port 5432
   ```

3. Create `.env` from the example:
   ```
   cp .env.example .env
   ```

4. Fill in the environment variables in `.env`:
   - `DB_CONNECTION_MODE=tcp`
   - `DB_HOST=127.0.0.1` (proxy default)
   - `DB_PORT=5432`
   - `DB_NAME`, `DB_USER`, `DB_PASSWORD`
   - `ALLOWED_ORIGINS=http://localhost:3000`
   - `EMBEDDING_MODEL=all-MiniLM-L6-v2`

5. Run the server:
   ```
   uvicorn main:app --reload --port 8000
   ```

   The API is available at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

## Database Connection

The backend connects to the same PostgreSQL database (Cloud SQL) used by the data pipeline. Connection mode is controlled by `DB_CONNECTION_MODE`:

- **`tcp`** (local dev): Connects via TCP, typically through Cloud SQL Auth Proxy on `127.0.0.1:5432`
- **`socket`** (production/Cloud Run): Connects via Unix socket at `/cloudsql/{INSTANCE_CONNECTION_NAME}`

When `USE_SECRET_MANAGER=true`, DB credentials are pulled from GCP Secret Manager instead of environment variables.

## Tables Used

- `processed_documents` — Main document content and metadata
- `interview_metadata` — Extracted entities (company, role, difficulty, outcome, topics)
- `companies` — Company lookup table
- `roles` — Role/title lookup table
- `document_chunks` — Chunked text with pgvector embeddings for semantic search
