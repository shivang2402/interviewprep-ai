"""
Tests for src/database/loader.py (BatchDBLoader).

Covers:
- load_batch with mocked GCS and DB: success count, success/failed lists
- Read failures (missing/invalid JSON) recorded in failed_reads
- Empty file list returns zero inserted
- _insert_doc: execute called with correct SQL and params (no real DB)
- _upsert_batch: on execute error, errors reflected in summary
"""

import pytest
from unittest.mock import MagicMock

from src.database.loader import BatchDBLoader
from src.database.queries import UPSERT_PROCESSED_DOC, UPSERT_INTERVIEW_META
from src.data_models.preprocessed_document import ProcessedInterviewDocument


class TestBatchDBLoaderInit:
    def test_init_loads_caches(self, mock_gcs, mock_db_conn):
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        assert loader.gcs is mock_gcs
        assert loader.conn is mock_db_conn
        assert loader.batch_size == 10
        assert mock_db_conn.cursor.called
        cur = mock_db_conn.cursor.return_value.__enter__.return_value
        assert cur.execute.call_count >= 2  # companies + roles


class TestBatchDBLoaderLoadBatch:
    def test_empty_file_list_returns_zero_inserted(self, mock_gcs, mock_db_conn):
        mock_gcs.list_files.return_value = []
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        summary = loader.load_batch("processed/bulk/")
        assert summary["total"] == 0
        assert summary["inserted"] == 0
        assert summary["skipped"] == 0
        assert summary["success"] == []
        assert summary["failed_reads"] == []
        assert summary["failed_inserts"] == []

    def test_successful_load_records_success_items(
        self, mock_gcs, mock_db_conn, processed_doc_dict
    ):
        mock_gcs.list_files.return_value = ["processed/bulk/doc1.json"]
        mock_gcs.read_json.return_value = processed_doc_dict
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        summary = loader.load_batch("processed/bulk/")
        assert summary["total"] == 1
        assert summary["inserted"] == 1
        assert summary["skipped"] == 0
        assert len(summary["success"]) == 1
        assert summary["success"][0]["path"] == "processed/bulk/doc1.json"
        assert summary["success"][0]["document_id"] == processed_doc_dict["document_id"]
        assert summary["success"][0]["title"] == processed_doc_dict["title"]

    def test_read_failure_recorded_in_failed_reads(
        self, mock_gcs, mock_db_conn, processed_doc_dict
    ):
        mock_gcs.list_files.return_value = ["processed/bulk/doc1.json", "processed/bulk/doc2.json"]
        # First file ok, second missing
        def read_json(path):
            if "doc2" in path:
                return None
            return processed_doc_dict
        mock_gcs.read_json.side_effect = read_json
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        summary = loader.load_batch("processed/bulk/")
        assert summary["total"] == 2
        assert summary["inserted"] == 1
        assert summary["skipped"] == 1
        assert len(summary["success"]) == 1
        assert len(summary["failed_reads"]) == 1
        assert summary["failed_reads"][0]["path"] == "processed/bulk/doc2.json"
        assert "missing" in summary["failed_reads"][0]["message"].lower() or "empty" in summary["failed_reads"][0]["message"].lower()  # noqa: E501

    def test_parse_failure_recorded_in_failed_reads(
        self, mock_gcs, mock_db_conn, processed_doc_dict
    ):
        mock_gcs.list_files.return_value = ["processed/bulk/doc1.json"]
        mock_gcs.read_json.return_value = {"invalid": "not a valid ProcessedInterviewDocument"}
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        summary = loader.load_batch("processed/bulk/")
        assert summary["total"] == 1
        assert summary["inserted"] == 0
        assert summary["skipped"] == 1
        assert len(summary["failed_reads"]) == 1
        assert summary["failed_reads"][0]["path"] == "processed/bulk/doc1.json"

    def test_custom_suffix(self, mock_gcs, mock_db_conn):
        mock_gcs.list_files.return_value = []
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        loader.load_batch("processed/bulk/", suffix=".json")
        mock_gcs.list_files.assert_called_once_with(prefix="processed/bulk/", suffix=".json")


class TestInsertDocExecuteCalls:
    """Assert _insert_doc (via load_batch) calls execute with correct SQL and params."""

    def test_execute_called_with_upsert_processed_doc_and_params(
        self, mock_gcs, mock_db_conn, processed_doc_dict
    ):
        mock_gcs.list_files.return_value = ["processed/bulk/doc1.json"]
        mock_gcs.read_json.return_value = processed_doc_dict
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        loader.load_batch("processed/bulk/")
        cur = mock_db_conn.cursor.return_value.__enter__.return_value
        calls = cur.execute.call_args_list
        # After _load_caches (2 selects), we have: UPSERT_PROCESSED_DOC, maybe INSERT role, UPSERT_INTERVIEW_META
        query_calls = [(c[0][0], c[0][1] if len(c[0]) > 1 else c[1]) for c in calls]
        processed_doc_calls = [c for c in query_calls if c[0] == UPSERT_PROCESSED_DOC]
        assert len(processed_doc_calls) == 1
        params = processed_doc_calls[0][1]
        assert params["document_id"] == processed_doc_dict["document_id"]
        assert params["title"] == processed_doc_dict["title"]
        assert params["source_platform"] == "leetcode"  # sanitized
        assert "content" in params
        assert "content_hash" in params

    def test_execute_called_with_upsert_interview_meta_when_company_role_present(
        self, mock_gcs, mock_db_conn, processed_doc_dict
    ):
        mock_gcs.list_files.return_value = ["processed/bulk/doc1.json"]
        mock_gcs.read_json.return_value = processed_doc_dict
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        loader.load_batch("processed/bulk/")
        cur = mock_db_conn.cursor.return_value.__enter__.return_value
        calls = cur.execute.call_args_list
        interview_meta_calls = [c for c in calls if len(c[0]) >= 2 and c[0][0] == UPSERT_INTERVIEW_META]
        assert len(interview_meta_calls) >= 1
        p = interview_meta_calls[0][0][1]  # (args, kwargs); args = (query, params)
        assert "document_id" in p
        assert "company_id" in p
        assert "role_id" in p
        assert p.get("experience_level") == "mid"
        assert p.get("interview_outcome") == "offer"
        assert p.get("difficulty") == "medium"
        assert "topics" in p


class TestUpsertBatchErrorPath:
    """_upsert_batch: when execute raises, errors show up in summary."""

    def test_execute_raise_recorded_in_failed_inserts(
        self, mock_gcs, mock_db_conn, processed_doc_dict
    ):
        mock_gcs.list_files.return_value = ["processed/bulk/doc1.json"]
        mock_gcs.read_json.return_value = processed_doc_dict
        cur = mock_db_conn.cursor.return_value.__enter__.return_value
        # Let _load_caches run (first 2 execute are selects), then raise on next execute
        call_count = [0]

        def raise_on_third(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                return None  # allow _load_caches
            raise Exception("duplicate key")

        cur.execute.side_effect = raise_on_third
        loader = BatchDBLoader(gcs_backend=mock_gcs, db_conn=mock_db_conn, batch_size=10)
        summary = loader.load_batch("processed/bulk/")
        assert summary["inserted"] == 0
        assert summary["skipped"] == 1
        assert len(summary["failed_inserts"]) == 1
        assert summary["failed_inserts"][0]["document_id"] == processed_doc_dict["document_id"]
        assert "duplicate" in summary["failed_inserts"][0]["message"].lower()
