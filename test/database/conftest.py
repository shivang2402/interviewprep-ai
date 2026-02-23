"""
Shared fixtures for database module tests.
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def processed_doc_dict():
    """Minimal dict that ProcessedInterviewDocument.from_dict() accepts."""
    return {
        "document_id": "leetcode_abc123",
        "source_platform": "leetcode",
        "source_url": "https://leetcode.com/discuss/post/123",
        "content_hash": "a" * 64,
        "title": "Google SDE2 Interview Experience",
        "content": "I interviewed at Google. Five rounds.",
        "word_count": 10,
        "company": "Google",
        "role": "Software Development Engineer",
        "experience_level": "mid",
        "interview_outcome": "offer",
        "difficulty": "medium",
        "num_rounds": 5,
        "interview_types": ["phone_screen", "onsite"],
        "topics": ["dsa", "system_design"],
        "published_at": "2026-01-15T10:00:00Z",
        "scraped_at": "2026-01-16T08:00:00Z",
        "scrape_batch_id": "2026-01-16_bulk",
        "source_metadata": {},
    }


@pytest.fixture
def load_summary_success_and_failure():
    """Sample load_batch summary with both success and failure entries."""
    return {
        "total": 3,
        "inserted": 2,
        "skipped": 1,
        "errors": [
            ("processed/bulk/doc3.json", "FileNotFoundError: missing"),
        ],
        "success": [
            {"path": "processed/bulk/doc1.json", "document_id": "leetcode_aaa", "title": "Title One"},
            {"path": "processed/bulk/doc2.json", "document_id": "leetcode_bbb", "title": "Title Two"},
        ],
        "failed_reads": [
            {"path": "processed/bulk/doc3.json", "message": "FileNotFoundError: missing"},
        ],
        "failed_inserts": [],
    }


@pytest.fixture
def mock_gcs():
    """GCS backend mock with list_files and read_json."""
    gcs = MagicMock()
    gcs.list_files.return_value = []
    gcs.read_json.return_value = None
    return gcs


@pytest.fixture
def mock_db_conn():
    """psycopg2 connection mock: cursor returns companies/roles for _load_caches."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    # _load_caches: first fetchall = companies, second = roles
    cur.fetchall.side_effect = [[(1, "google"), (2, "meta")], [(1, "swe"), (2, "sde")]]
    cur.fetchone.return_value = (99,)  # for _get_or_create_company/role insert
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn
