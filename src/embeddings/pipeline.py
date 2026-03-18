"""
Embedding Pipeline
-------------------
1. For each model, find chunks missing that model's embedding column
2. Generate embeddings for all models in one pass per chunk batch
3. UPDATE the embedding columns in document_chunks
4. Write manifest to GCS

Prerequisites:
    CREATE EXTENSION IF NOT EXISTS vector;

    -- Add embedding columns (run once per model):
    ALTER TABLE public.document_chunks
        ADD COLUMN IF NOT EXISTS embedding_all_minilm_l6_v2 vector(384);
    ALTER TABLE public.document_chunks
        ADD COLUMN IF NOT EXISTS embedding_all_mpnet_base_v2 vector(768);

Run:
    python -m src.embeddings.pipeline
"""

import logging
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import time
print("1--"+ time.asctime())
from sentence_transformers import SentenceTransformer
print("2--"+ time.asctime())

from src.storage.gcs_backend import GCSBackend
print("3"+ time.asctime())

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

MODELS = [
    "all-MiniLM-L6-v2",       # 384-dim
    "all-mpnet-base-v2",       # 768-dim
]

ENCODE_BATCH = 256   # sentences per model.encode() call
DB_BATCH     = 500   # rows per UPDATE round-trip


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def embedding_column_name(model: str) -> str:
    return f"embedding_{model.replace('-', '_')}".lower()


# ---------------------------------------------------------------------------
# Fetch chunks that are missing ANY model's embedding
# ---------------------------------------------------------------------------

def fetch_chunks_missing_embeddings(conn, models: list[str]) -> list[dict]:
    """
    Return chunks where at least one embedding column is NULL.
    """
    columns = [embedding_column_name(m) for m in models]
    where_clauses = " OR ".join(f"{col} IS NULL" for col in columns)

    sql = f"""
        SELECT chunk_id, chunk_text
        FROM public.document_chunks
        WHERE {where_clauses}
        ORDER BY chunk_id
    """

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    log.info(f"Fetched {len(rows):,} chunks missing embeddings")
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Update embeddings in document_chunks
# ---------------------------------------------------------------------------

def update_embeddings(conn, columns: list[str], rows: list[tuple]):
    """
    rows: list of (embedding_col1_vec, embedding_col2_vec, ..., chunk_id)
    """
    set_clause = ", ".join(f"{col} = data.{col}" for col in columns)
    col_defs   = ", ".join(f"{col} vector" for col in columns)
    placeholders = ", ".join(["%s"] * (len(columns) + 1))  # +1 for chunk_id

    sql = f"""
        UPDATE public.document_chunks AS dc
        SET {set_clause}
        FROM (VALUES ({placeholders}))
            AS data(chunk_id, {", ".join(columns)})
        WHERE dc.chunk_id = data.chunk_id
    """

    # Reorder rows: (chunk_id, emb1, emb2, ...) for the VALUES clause
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(sql, row)
    conn.commit()


def update_embeddings_batch(conn, columns: list[str], rows: list[tuple]):
    """
    Batch update using executemany.
    Each row: (emb_col1_vec, emb_col2_vec, ..., chunk_id)
    """
    set_clause = ", ".join(f"{col} = %s" for col in columns)
    sql = f"""
        UPDATE public.document_chunks
        SET {set_clause}
        WHERE chunk_id = %s
    """

    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()


# ---------------------------------------------------------------------------
# Write manifest to GCS
# ---------------------------------------------------------------------------

def write_manifest(gcs_backend: GCSBackend, stats: dict):
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = f"embedding_manifests/manifest_{ts}.json"
    gcs_backend.write_json(path, stats)
    log.info(f"Manifest written to GCS: {path}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(models: list[str] = MODELS):
    log.info(f"Starting embedding pipeline for models: {models}")

    conn = psycopg2.connect(**DB_CONFIG)
    log.info("Connected to Cloud SQL")

    gcs_backend = GCSBackend(
        bucket_name = GCS_BUCKET,
        project_id  = GCS_PROJECT,
        secret_name = GCS_SECRET,
    )

    # Load all models upfront
    loaded_models = {}
    for model_name in models:
        log.info(f"Loading model: {model_name}")
        loaded_models[model_name] = SentenceTransformer(model_name)
        dim = loaded_models[model_name].get_sentence_embedding_dimension()
        log.info(f"  {model_name} loaded — dim={dim}")

    # Fetch chunks missing any embedding
    chunks = fetch_chunks_missing_embeddings(conn, models)
    if not chunks:
        log.info("All chunks already embedded. Exiting.")
        conn.close()
        return

    columns = [embedding_column_name(m) for m in models]

    stats = {
        "models":           models,
        "run_at":           datetime.now(timezone.utc).isoformat(),
        "chunks_embedded":  0,
        "errors":           [],
    }

    db_batch = []

    for i in range(0, len(chunks), ENCODE_BATCH):
        batch = chunks[i : i + ENCODE_BATCH]
        texts = [c["chunk_text"] for c in batch]
        ids   = [c["chunk_id"]   for c in batch]

        try:
            # Generate embeddings for all models on this batch
            all_vectors = {}
            for model_name in models:
                vectors = loaded_models[model_name].encode(
                    texts,
                    batch_size           = ENCODE_BATCH,
                    show_progress_bar    = False,
                    normalize_embeddings = True,
                )
                all_vectors[model_name] = vectors

            # Build rows: (emb1, emb2, ..., chunk_id)
            for j, chunk_id in enumerate(ids):
                row = tuple(
                    all_vectors[m][j].tolist() for m in models
                ) + (chunk_id,)
                db_batch.append(row)

            stats["chunks_embedded"] += len(batch)

            # Flush to DB when batch is large enough
            if len(db_batch) >= DB_BATCH:
                update_embeddings_batch(conn, columns, db_batch)
                log.info(f"  Updated {stats['chunks_embedded']:,} / {len(chunks):,}")
                db_batch = []

        except Exception as e:
            log.error(f"Batch starting at {i} failed: {e}")
            stats["errors"].append({"batch_start": i, "error": str(e)})

    # Flush remaining
    if db_batch:
        update_embeddings_batch(conn, columns, db_batch)

    conn.close()

    log.info("=" * 50)
    log.info(f"Models         : {models}")
    log.info(f"Chunks embedded: {stats['chunks_embedded']:,}")
    log.info(f"Errors         : {len(stats['errors'])}")

    write_manifest(gcs_backend, stats)


if __name__ == "__main__":
    log.info("Hi There!")
    run()