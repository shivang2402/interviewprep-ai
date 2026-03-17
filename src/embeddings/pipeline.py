"""
Embedding Pipeline
-------------------
1. Read chunks from document_chunks (where embedding not yet generated)
2. Generate embeddings using all-MiniLM-L6-v2 (384-dim)
3. Store embeddings in chunk_embeddings table
4. Write manifest to GCS

Note: chunk_embeddings table must already exist in Cloud SQL.
      See schema below.

SQL to run in Cloud SQL console before this:
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS public.chunk_embeddings (
        chunk_id        text    NOT NULL REFERENCES public.document_chunks(chunk_id) ON DELETE CASCADE,
        embedding_model text    NOT NULL,
        embedding       vector(384) NOT NULL,
        embedded_at     timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (chunk_id, embedding_model)
    );

    CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model
        ON public.chunk_embeddings (embedding_model);

    CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_vector
        ON public.chunk_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);

Run:
    pip install sentence-transformers psycopg2-binary
    python -m src.embeddings.pipeline
"""

import logging
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer

from src.storage.gcs_backend import GCSBackend

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host":     "34.148.0.165",
    "dbname":   "interviewprep-ai-database",
    "user":     "postgres",
    "password": "admin",
    "port":     5432,
    "sslmode":  "require",
}

GCS_BUCKET  = "interviewprep-ai-data"
GCS_PROJECT = "professorbot-dovbsg"
GCS_SECRET  = "gcs-service-account-key"

MODEL_NAME  = "all-MiniLM-L6-v2"          # Model 1 — done
# MODEL_NAME  = "multi-qa-MiniLM-L6-cos-v1" # Model 2 — QA-specific, 384-dim
# MODEL_NAME  = "all-mpnet-base-v2"          # Model 3 — best general, 768-dim
BATCH_SIZE  = 256
DB_BATCH    = 500


# ---------------------------------------------------------------------------
# Fetch un-embedded chunks
# ---------------------------------------------------------------------------

FETCH_SQL = """
SELECT
    dc.chunk_id,
    dc.chunk_text
FROM public.document_chunks dc
WHERE NOT EXISTS (
    SELECT 1 FROM public.chunk_embeddings ce
    WHERE ce.chunk_id = dc.chunk_id
      AND ce.embedding_model = %(model)s
)
ORDER BY dc.chunk_id
"""


def fetch_chunks(conn, model: str) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(FETCH_SQL, {"model": model})
        rows = cur.fetchall()
    log.info(f"Fetched {len(rows):,} un-embedded chunks for model={model}")
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Insert embeddings
# ---------------------------------------------------------------------------

INSERT_SQL = """
INSERT INTO public.chunk_embeddings (chunk_id, embedding_model, embedding)
VALUES %s
ON CONFLICT (chunk_id, embedding_model) DO NOTHING
"""


def insert_embeddings(conn, rows: list[tuple]):
    with conn.cursor() as cur:
        execute_values(cur, INSERT_SQL, rows)
    conn.commit()


# ---------------------------------------------------------------------------
# Write manifest
# ---------------------------------------------------------------------------

def write_manifest(gcs_backend: GCSBackend, stats: dict):
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = f"embedding_manifests/manifest_{stats['model']}_{ts}.json"
    gcs_backend.write_json(path, stats)
    log.info(f"Manifest written to GCS: {path}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(model_name: str = MODEL_NAME):
    conn = psycopg2.connect(**DB_CONFIG)
    log.info("Connected to Cloud SQL")

    gcs_backend = GCSBackend(
        bucket_name = GCS_BUCKET,
        project_id  = GCS_PROJECT,
        secret_name = GCS_SECRET,
    )

    # Load model
    log.info(f"Loading model: {model_name}")
    model = SentenceTransformer(model_name)
    log.info(f"Model loaded — embedding dim: {model.get_sentence_embedding_dimension()}")

    chunks = fetch_chunks(conn, model_name)
    if not chunks:
        log.info("No chunks to embed. Exiting.")
        conn.close()
        return

    stats = {
        "model":            model_name,
        "run_at":           datetime.now(timezone.utc).isoformat(),
        "chunks_embedded":  0,
        "errors":           [],
    }

    db_batch = []

    for i in range(0, len(chunks), BATCH_SIZE):
        batch   = chunks[i: i + BATCH_SIZE]
        texts   = [c["chunk_text"] for c in batch]
        ids     = [c["chunk_id"]   for c in batch]

        try:
            vectors = model.encode(
                texts,
                batch_size      = BATCH_SIZE,
                show_progress_bar = False,
                normalize_embeddings = True,   # cosine similarity → dot product
            )

            for chunk_id, vector in zip(ids, vectors):
                db_batch.append((chunk_id, model_name, vector.tolist()))

            stats["chunks_embedded"] += len(batch)

            if len(db_batch) >= DB_BATCH:
                insert_embeddings(conn, db_batch)
                log.info(f"  Embedded {stats['chunks_embedded']:,} / {len(chunks):,}")
                db_batch = []

        except Exception as e:
            log.error(f"Batch {i} failed: {e}")
            stats["errors"].append({"batch_start": i, "error": str(e)})

    # Flush remaining
    if db_batch:
        insert_embeddings(conn, db_batch)

    conn.close()

    log.info("=" * 50)
    log.info(f"Model          : {model_name}")
    log.info(f"Chunks embedded: {stats['chunks_embedded']:,}")
    log.info(f"Errors         : {len(stats['errors'])}")

    write_manifest(gcs_backend, stats)


if __name__ == "__main__":
    run()





## PENDING ivfflat task !!!!!!!