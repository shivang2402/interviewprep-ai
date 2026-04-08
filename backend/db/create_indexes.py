import logging

from db.connection import get_connection

logger = logging.getLogger(__name__)

INDEXES = [
    (
        "idx_fts_documents",
        """
        CREATE INDEX IF NOT EXISTS idx_fts_documents
        ON public.processed_documents
        USING GIN(to_tsvector('english', coalesce(title,'') || ' ' || coalesce(cleaned_content,'')))
        """,
    ),
    (
        "idx_embedding_minilm",
        """
        CREATE INDEX IF NOT EXISTS idx_embedding_minilm
        ON public.document_chunks
        USING ivfflat (embeddings_all_minilm_l6_v2 vector_cosine_ops)
        WITH (lists = 100)
        """,
    ),
]


def create_indexes():
    with get_connection() as conn:
        with conn.cursor() as cur:
            for name, ddl in INDEXES:
                try:
                    cur.execute(ddl)
                    logger.info("Index ensured: %s", name)
                except Exception:
                    logger.exception("Failed to create index %s", name)
                    conn.rollback()
