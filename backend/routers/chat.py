import logging
import os
from concurrent.futures import ThreadPoolExecutor

import psycopg2
from fastapi import APIRouter, HTTPException

from models.schemas import QueryRequest, QueryResponse, ChunkSource, TokenUsage

logger = logging.getLogger(__name__)

router = APIRouter()

# Populated by main.py on startup
_generator = None
_log_executor = ThreadPoolExecutor(max_workers=2)


def set_generator(generator):
    global _generator
    _generator = generator


def _get_log_connection():
    """Get a DB connection for logging using env vars."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "34.148.0.165"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "interviewprep-ai-database"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "admin"),
    )


CREATE_LOG_TABLE = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS query_logs (
    id              SERIAL PRIMARY KEY,
    query_text      TEXT NOT NULL,
    query_embedding vector(384) NOT NULL,
    top_k_chunk_ids INTEGER[] NOT NULL,
    top_k_scores    FLOAT[] NOT NULL,
    latency_ms      INTEGER NOT NULL,
    llm_response    TEXT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_query_logs_timestamp ON query_logs (timestamp DESC);
"""

INSERT_LOG = """
INSERT INTO query_logs
    (query_text, query_embedding, top_k_chunk_ids, top_k_scores,
     latency_ms, llm_response)
VALUES (%s, %s::vector, %s, %s, %s, %s);
"""


def ensure_log_table():
    """Create the query_logs table if it doesn't exist."""
    try:
        conn = _get_log_connection()
        with conn.cursor() as cur:
            cur.execute(CREATE_LOG_TABLE)
        conn.commit()
        conn.close()
        logger.info("query_logs table ensured")
    except Exception:
        logger.exception("Failed to create query_logs table")


def _log_query(result: dict):
    """Write query telemetry to PostgreSQL (fire-and-forget)."""
    try:
        chunks = result.get("chunks", [])
        chunk_ids = [int(c["id"]) if str(c.get("id", "")).isdigit() else 0 for c in chunks]
        scores = [c.get("score", 0.0) for c in chunks]
        embedding = result.get("query_embedding")
        embedding_list = embedding.tolist() if embedding is not None else None

        conn = _get_log_connection()
        with conn.cursor() as cur:
            cur.execute(INSERT_LOG, (
                result["query"],
                embedding_list,
                chunk_ids,
                scores,
                int(result.get("latency_ms", 0)),
                result.get("answer", ""),
            ))
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("Failed to log query")


@router.post("/chat", response_model=QueryResponse)
def chat(req: QueryRequest):
    if _generator is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")

    try:
        result = _generator.generate(req.message)
    except Exception:
        logger.exception("RAG generation failed")
        raise HTTPException(status_code=500, detail="Failed to generate response")

    # Part B: fire-and-forget async log to PostgreSQL via background thread
    _log_executor.submit(_log_query, result)

    sources = [
        ChunkSource(
            chunk_id=chunk.get("id"),
            company=chunk.get("company"),
            role=chunk.get("role"),
            source_url=chunk.get("source_url"),
            score=chunk.get("score"),
        )
        for chunk in result.get("chunks", [])
    ]

    return QueryResponse(
        answer=result["answer"],
        sources=sources,
        usage=TokenUsage(**result["usage"]),
        latency_ms=result.get("latency_ms", 0),
    )
