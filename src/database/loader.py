"""Batch loader: GCS → PostgreSQL upsert for processed interview documents."""

import json
import logging
from datetime import datetime, timezone

from psycopg2.extensions import connection as PgConnection

from src.storage.gcs_backend import GCSBackend
from src.data_models.preprocessed_document import ProcessedInterviewDocument

from src.database.queries import UPSERT_PROCESSED_DOC, UPSERT_INTERVIEW_META
from src.database.sanitizers import (
    db_platform,
    db_enum,
    DB_EXPERIENCE_VALID,
    DB_OUTCOME_VALID,
    DB_DIFFICULTY_VALID,
    DB_INTERVIEW_TYPE_VALID,
)

logger = logging.getLogger(__name__)


class BatchDBLoader:
    """
    Reads processed JSON files from a GCS bucket folder and upserts
    them into Cloud SQL (PostgreSQL).

    Usage:
        loader = BatchDBLoader(
            gcs_backend=GCSBackend(...),
            db_conn=psycopg2.connect(...),
        )
        result = loader.load_batch("processed/2026-02-16_bulk/")
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
            (name.strip(),),
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
            (title.strip(),),
        )
        role_id = cur.fetchone()[0]
        self._role_cache[key] = role_id
        print(f"[BatchDBLoader] New role inserted: '{title}' → id={role_id}")
        return role_id

    def load_batch(self, gcs_prefix: str, suffix: str = ".json") -> dict:
        files = self.gcs.list_files(prefix=gcs_prefix, suffix=suffix)

        files = files[:2]
        logger.info(f"[BatchDBLoader] Found {len(files)} files under '{gcs_prefix}'")
        summary = {"total": len(files), "inserted": 0, "skipped": 0, "errors": []}

        for chunk_start in range(0, len(files), self.batch_size):
            chunk = files[chunk_start : chunk_start + self.batch_size]
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
            summary["skipped"] += len(errs)
            summary["errors"].extend(errs)

        logger.info(
            f"[BatchDBLoader] Done — inserted={summary['inserted']}, "
            f"skipped={summary['skipped']}, total={summary['total']}"
        )
        return summary

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
        cur.execute(UPSERT_PROCESSED_DOC, {
            "document_id": doc.document_id,
            "source_platform": db_platform(doc.source_platform),
            "source_url": doc.source_url,
            "content_hash": doc.content_hash,
            "title": doc.title,
            "content": doc.content,
            "word_count": doc.word_count,
            "published_at": doc.published_at,
            "scraped_at": doc.scraped_at or datetime.now(timezone.utc).isoformat(),
            "preprocessed_at": doc.preprocessed_at,
            "scrape_batch_id": doc.scrape_batch_id,
            "source_metadata": json.dumps(doc.source_metadata or {}),
        })
        if doc.company and doc.role:
            interview_type = doc.interview_types[0] if doc.interview_types else None
            company_id = self._get_or_create_company(cur, doc.company)
            role_id = self._get_or_create_role(cur, doc.role)
            cur.execute(UPSERT_INTERVIEW_META, {
                "document_id": doc.document_id,
                "company_id": company_id,
                "role_id": role_id,
                "experience_level": db_enum(doc.experience_level, DB_EXPERIENCE_VALID),
                "interview_outcome": db_enum(doc.interview_outcome, DB_OUTCOME_VALID),
                "difficulty": db_enum(doc.difficulty, DB_DIFFICULTY_VALID),
                "num_rounds": doc.num_rounds,
                "interview_type": db_enum(interview_type, DB_INTERVIEW_TYPE_VALID),
                "topics": list(doc.topics) if doc.topics else [],
            })
