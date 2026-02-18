import json
import logging
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2.extensions import connection as PgConnection

from src.storage.gcs_backend import GCSBackend
from src.data_models.preprocessed_document import ProcessedInterviewDocument

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# SQL helpers
# ─────────────────────────────────────────────

_UPSERT_PROCESSED_DOC = """
INSERT INTO public.processed_documents (
    document_id, source_platform, source_url, content_hash,
    title, cleaned_content, word_count,
    published_at, scraped_at, processed_at,
    scrape_batch_id, source_metadata
)
VALUES (
    %(document_id)s,
    %(source_platform)s::public.source_platform_enum,
    %(source_url)s,
    %(content_hash)s,
    %(title)s,
    %(content)s,
    %(word_count)s,
    %(published_at)s,
    %(scraped_at)s,
    %(preprocessed_at)s,
    %(scrape_batch_id)s,
    %(source_metadata)s::jsonb
)
ON CONFLICT (document_id) DO UPDATE SET
    content_hash    = EXCLUDED.content_hash,
    cleaned_content = EXCLUDED.cleaned_content,
    word_count      = EXCLUDED.word_count,
    processed_at    = EXCLUDED.processed_at,
    source_metadata = EXCLUDED.source_metadata;
"""

_UPSERT_INTERVIEW_META = """
INSERT INTO public.interview_metadata (
    document_id, company_id, role_id,
    experience_level, interview_outcome, difficulty,
    num_rounds, interview_type, topics
)
VALUES (
    %(document_id)s,
    %(company_id)s,
    %(role_id)s,
    %(experience_level)s::public.experience_level_enum,
    %(interview_outcome)s::public.interview_outcome_enum,
    %(difficulty)s::public.difficulty_enum,
    %(num_rounds)s,
    %(interview_type)s::public.interview_type_enum,
    %(topics)s::text[]
)
ON CONFLICT (document_id) DO UPDATE SET
    company_id         = EXCLUDED.company_id,
    role_id            = EXCLUDED.role_id,
    experience_level   = EXCLUDED.experience_level,
    interview_outcome  = EXCLUDED.interview_outcome,
    difficulty         = EXCLUDED.difficulty,
    num_rounds         = EXCLUDED.num_rounds,
    interview_type     = EXCLUDED.interview_type,
    topics             = EXCLUDED.topics;
"""

# ─────────────────────────────────────────────
# DB enum value sanitizers
# ─────────────────────────────────────────────

_DB_EXPERIENCE_VALID     = {"intern", "entry", "mid", "senior", "staff", "leadership"}
_DB_OUTCOME_VALID        = {"offer", "reject", "pending"}
_DB_DIFFICULTY_VALID     = {"easy", "medium", "hard"}
_DB_INTERVIEW_TYPE_VALID = {"phone_screen", "onsite", "online_assessment", "virtual", "on_campus", "off_campus", "walk_in"}  # FIX 3

# FIX 1: DB stores 'gfg', not 'geeksforgeeks'
_PLATFORM_TO_DB = {
    "leetcode":      "leetcode",
    "geeksforgeeks": "gfg",
    "medium":        "medium",
}

def _db_platform(value: str) -> str:
    """Map Python-normalized platform name → DB enum value."""
    return _PLATFORM_TO_DB.get(value, value)

def _db_enum(value: Optional[str], valid: set) -> Optional[str]:
    """
    FIX 2: Strip values that exist in Python model but NOT in DB enums
    (e.g. 'unknown'). Returns None so psycopg2 inserts NULL instead of
    crashing with an invalid enum cast.
    """
    if value is None:
        return None
    return value if value in valid else None


# ─────────────────────────────────────────────
# Main loader class
# ─────────────────────────────────────────────

class BatchDBLoader:
    """
    Reads processed JSON files from a GCS bucket folder and upserts
    them into Cloud SQL (PostgreSQL).

    Usage:
        loader = BatchDBLoader(
            gcs_backend=GCSBackend(
                bucket_name="interviewprep-ai-data",
                project_id="professorbot-dovbsg",
                secret_name="gcs-service-account-key",
            ),
            db_conn=psycopg2.connect(
                host="<CLOUD_SQL_PUBLIC_IP>",
                dbname="interviewprep",
                user="postgres",
                password="<PASSWORD>",
            ),
        )

        result = loader.load_batch("processed/2026-02-16_bulk/")
        print(result)
    """

    def __init__(
        self,
        gcs_backend: GCSBackend,
        db_conn: PgConnection,
        batch_size: int = 50,
    ):
        self.gcs = gcs_backend
        self.conn = db_conn
        self.batch_size = batch_size

        self._company_cache: dict[str, int] = {}
        self._role_cache: dict[str, int] = {}
        self._load_caches()

    def _load_caches(self) -> None:
        """Load all existing companies and roles into memory once at startup."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT company_id, LOWER(name) FROM public.companies;")
            self._company_cache = {name: cid for cid, name in cur.fetchall()}

            cur.execute("SELECT role_id, LOWER(title) FROM public.roles;")
            self._role_cache = {title: rid for rid, title in cur.fetchall()}

        print(f"[BatchDBLoader] Cache loaded — {len(self._company_cache)} companies, {len(self._role_cache)} roles")

    def _get_or_create_company(self, cur, name: str) -> int:
        key = name.lower().strip()
        if key in self._company_cache:
            return self._company_cache[key]

        cur.execute(
            "INSERT INTO public.companies (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING company_id;",
            (name.strip(),)
        )
        company_id = cur.fetchone()[0]
        self._company_cache[key] = company_id
        print(f"[BatchDBLoader] New company inserted: '{name}' → id={company_id}")
        return company_id

    def _get_or_create_role(self, cur, title: str) -> int:
        key = title.lower().strip()
        if key in self._role_cache:
            return self._role_cache[key]

        cur.execute(
            "INSERT INTO public.roles (title) VALUES (%s) ON CONFLICT (title) DO UPDATE SET title = EXCLUDED.title RETURNING role_id;",
            (title.strip(),)
        )
        role_id = cur.fetchone()[0]
        self._role_cache[key] = role_id
        print(f"[BatchDBLoader] New role inserted: '{title}' → id={role_id}")
        return role_id

    # ─── Public API ───────────────────────────

    def load_batch(self, gcs_prefix: str, suffix: str = ".json") -> dict:
        files = self.gcs.list_files(prefix=gcs_prefix, suffix=suffix)
        # files = files[:2] testing
        logger.info(f"[BatchDBLoader] Found {len(files)} files under '{gcs_prefix}'")

        summary = {"total": len(files), "inserted": 0, "skipped": 0, "errors": []}

        for chunk_start in range(0, len(files), self.batch_size):
            chunk = files[chunk_start: chunk_start + self.batch_size]
            docs = []

            for path in chunk:
                try:
                    raw = self.gcs.read_json(path)
                    if raw is None:
                        raise FileNotFoundError(f"Empty / missing blob: {path}")
                    doc = ProcessedInterviewDocument.from_dict(raw)
                    docs.append(doc)
                except Exception as e:
                    logger.warning(f"[BatchDBLoader] Skipping {path}: {e}")
                    summary["skipped"] += 1
                    summary["errors"].append((path, str(e)))

            if not docs:
                continue

            inserted, errs = self._upsert_batch(docs)
            summary["inserted"] += inserted
            summary["skipped"]  += len(errs)
            summary["errors"].extend(errs)

        logger.info(
            f"[BatchDBLoader] Done — inserted={summary['inserted']}, "
            f"skipped={summary['skipped']}, total={summary['total']}"
        )
        return summary

    # ─── Private helpers ──────────────────────

    def _upsert_batch(self, docs: list[ProcessedInterviewDocument]) -> tuple[int, list]:
        inserted, errors = 0, []

        try:
            with self.conn:
                with self.conn.cursor() as cur:
                    for doc in docs:
                        try:
                            self._insert_doc(cur, doc)
                            inserted += 1
                        except Exception as e:
                            logger.error(f"[BatchDBLoader] Row error for {doc.document_id}: {e}")
                            errors.append((doc.document_id, str(e)))
                            self.conn.rollback()
        except Exception as e:
            logger.error(f"[BatchDBLoader] Batch-level DB error: {e}")
            errors.extend([(d.document_id, str(e)) for d in docs])
            inserted = 0

        return inserted, errors

    def _insert_doc(self, cur, doc: ProcessedInterviewDocument) -> None:
        """Upserts one document into processed_documents + interview_metadata."""

        # ── 1. processed_documents ──
        cur.execute(_UPSERT_PROCESSED_DOC, {
            "document_id":     doc.document_id,
            "source_platform": _db_platform(doc.source_platform),
            "source_url":      doc.source_url,
            "content_hash":    doc.content_hash,
            "title":           doc.title,
            "content":         doc.content,
            "word_count":      doc.word_count,
            "published_at":    doc.published_at,
            "scraped_at":      doc.scraped_at or datetime.now(timezone.utc).isoformat(),
            "preprocessed_at": doc.preprocessed_at,
            "scrape_batch_id": doc.scrape_batch_id,
            "source_metadata": json.dumps(doc.source_metadata or {}),
        })

        # ── 2. interview_metadata (only if company / role are present) ──
        if doc.company and doc.role:
            interview_type = (
                doc.interview_types[0] if doc.interview_types else None
            )

            company_id = self._get_or_create_company(cur, doc.company)
            role_id    = self._get_or_create_role(cur, doc.role)

            cur.execute(_UPSERT_INTERVIEW_META, {
                "document_id":       doc.document_id,
                "company_id":        company_id,
                "role_id":           role_id,
                "experience_level":  _db_enum(doc.experience_level, _DB_EXPERIENCE_VALID),
                "interview_outcome": _db_enum(doc.interview_outcome, _DB_OUTCOME_VALID),
                "difficulty":        _db_enum(doc.difficulty, _DB_DIFFICULTY_VALID),
                "num_rounds":        doc.num_rounds,
                "interview_type":    _db_enum(interview_type, _DB_INTERVIEW_TYPE_VALID),  # FIX 3
                "topics":            list(doc.topics) if doc.topics else [],
            })


# ─────────────────────────────────────────────
# CLI convenience
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import os

    storage = GCSBackend(
        bucket_name="interviewprep-ai-data",
        project_id="professorbot-dovbsg",
        secret_name="gcs-service-account-key",
    )

    conn = psycopg2.connect(
        host="34.148.0.165",
        dbname="interviewprep-ai-database",
        user="postgres",
        password="admin",
        port=5432,
        sslmode="require",
    )

    print("✅ Connected to DB!")
    print(conn)

    loader = BatchDBLoader(gcs_backend=storage, db_conn=conn, batch_size=50)
    result = loader.load_batch("processed/2026-02-16_bulk/")
    print(json.dumps(result, indent=2))

    conn.close()