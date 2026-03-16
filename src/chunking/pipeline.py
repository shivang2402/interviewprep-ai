"""
Chunking Pipeline
------------------
1. Read processed_documents from Cloud SQL
2. Join with interview_metadata for company / role / etc
3. Run chunk_document() on each doc
4. Write chunks to document_chunks table in Cloud SQL
5. Write a manifest JSON to GCS (audit trail)

Note: document_chunks table must already exist in Cloud SQL
      (created manually via SQL console before running this).

Run:
    python -m src.chunking.pipeline
"""

import logging
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values

from src.chunking.chunk import chunk_document, DocumentChunk
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

BATCH_SIZE  = 100


# ---------------------------------------------------------------------------
# Fetch un-chunked docs from Cloud SQL
# ---------------------------------------------------------------------------

FETCH_SQL = """
SELECT
    pd.document_id,
    pd.source_platform,
    pd.cleaned_content,
    pd.word_count,
    c.name   AS company,
    r.title  AS role,
    im.experience_level,
    im.interview_outcome,
    im.difficulty,
    im.interview_type,
    im.topics
FROM public.processed_documents pd
LEFT JOIN public.interview_metadata im USING (document_id)
LEFT JOIN public.companies c  ON im.company_id = c.company_id
LEFT JOIN public.roles     r  ON im.role_id    = r.role_id
WHERE pd.document_id NOT IN (
    SELECT DISTINCT document_id FROM public.document_chunks
)
ORDER BY pd.document_id
"""


def fetch_docs(conn) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(FETCH_SQL)
        rows = cur.fetchall()
    log.info(f"Fetched {len(rows):,} un-chunked documents")
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Insert chunks into Cloud SQL
# ---------------------------------------------------------------------------

INSERT_SQL = """
INSERT INTO public.document_chunks (
    chunk_id, document_id, chunk_index, total_chunks,
    chunk_text, raw_text, word_count,
    char_start_offset, char_end_offset,
    round_label, strategy, source_platform,
    company, role, experience_level,
    interview_outcome, difficulty, interview_type, topics
) VALUES %s
ON CONFLICT (chunk_id) DO NOTHING
"""


def insert_chunks(conn, chunks: list[DocumentChunk]):
    rows = [
        (
            c.chunk_id,
            c.document_id,
            c.chunk_index,
            c.total_chunks,
            c.chunk_text,
            c.raw_text,
            c.word_count,
            c.char_start_offset,
            c.char_end_offset,
            c.round_label,
            c.strategy,
            c.source_platform,
            c.company,
            c.role,
            c.experience_level,
            c.interview_outcome,
            c.difficulty,
            c.interview_type,
            c.topics or [],
        )
        for c in chunks
    ]
    with conn.cursor() as cur:
        execute_values(cur, INSERT_SQL, rows)
    conn.commit()


# ---------------------------------------------------------------------------
# Write manifest to GCS
# ---------------------------------------------------------------------------

def write_manifest(gcs_backend: GCSBackend, stats: dict):
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = f"chunking_manifests/manifest_{ts}.json"
    gcs_backend.write_json(path, {
        "run_at":          ts,
        "docs_processed":  stats["docs_processed"],
        "chunks_created":  stats["chunks_created"],
        "errors":          stats["errors"],
        "strategy_counts": stats["strategy_counts"],
    })
    log.info(f"Manifest written to GCS: {path}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run():
    conn = psycopg2.connect(**DB_CONFIG)
    log.info("Connected to Cloud SQL")

    gcs_backend = GCSBackend(
        bucket_name = GCS_BUCKET,
        project_id  = GCS_PROJECT,
        secret_name = GCS_SECRET,
    )

    docs = fetch_docs(conn)
    if not docs:
        log.info("No new documents to chunk. Exiting.")
        conn.close()
        return

    stats = {
        "docs_processed":  0,
        "chunks_created":  0,
        "errors":          [],
        "strategy_counts": {"structural": 0, "fixed_window": 0, "single_chunk": 0},
    }

    batch: list[DocumentChunk] = []

    docs = docs[:5]

    for doc in docs:
        try:
            chunks = chunk_document(
                document_id       = doc["document_id"],
                cleaned_content   = doc["cleaned_content"],
                source_platform   = doc["source_platform"],
                company           = doc.get("company"),
                role              = doc.get("role"),
                experience_level  = doc.get("experience_level"),
                interview_outcome = doc.get("interview_outcome"),
                difficulty        = doc.get("difficulty"),
                interview_type    = doc.get("interview_type"),
                topics            = list(doc["topics"]) if doc.get("topics") else [],
            )

            batch.extend(chunks)
            stats["docs_processed"] += 1
            stats["chunks_created"] += len(chunks)

            if chunks:
                stats["strategy_counts"][chunks[0].strategy] += 1

            if len(batch) >= BATCH_SIZE:
                insert_chunks(conn, batch)
                log.info(
                    f"  Committed batch | "
                    f"docs={stats['docs_processed']:,} "
                    f"chunks={stats['chunks_created']:,}"
                )
                batch = []

        except Exception as e:
            log.error(f"Error on {doc['document_id']}: {e}")
            stats["errors"].append({
                "document_id": doc["document_id"],
                "error":       str(e),
            })

    # Flush remaining batch
    if batch:
        insert_chunks(conn, batch)

    conn.close()

    log.info("=" * 50)
    log.info(f"Docs processed : {stats['docs_processed']:,}")
    log.info(f"Chunks created : {stats['chunks_created']:,}")
    log.info(f"Errors         : {len(stats['errors'])}")
    log.info(f"Strategy breakdown: {stats['strategy_counts']}")

    write_manifest(gcs_backend, stats)


if __name__ == "__main__":
    run()