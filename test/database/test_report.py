"""
Tests for src/database/report.py

Covers build_load_report():
- Report structure (report_type, completed_at, source_prefix, summary, success, failures)
- Summary counts match input
- success.items and failure items passed through
"""

import pytest
from datetime import datetime, timezone

from src.database.report import build_load_report


class TestBuildLoadReportStructure:
    def test_returns_dict_with_expected_keys(self, load_summary_success_and_failure):
        report = build_load_report(load_summary_success_and_failure, "processed/bulk/")
        assert "report_type" in report
        assert "completed_at" in report
        assert "source_prefix" in report
        assert "summary" in report
        assert "success" in report
        assert "failures" in report

    def test_report_type_is_db_load(self, load_summary_success_and_failure):
        report = build_load_report(load_summary_success_and_failure, "processed/bulk/")
        assert report["report_type"] == "db_load"

    def test_source_prefix_preserved(self, load_summary_success_and_failure):
        report = build_load_report(load_summary_success_and_failure, "processed/2026-02-16_bulk/")
        assert report["source_prefix"] == "processed/2026-02-16_bulk/"

    def test_completed_at_is_iso_format(self, load_summary_success_and_failure):
        report = build_load_report(load_summary_success_and_failure, "processed/bulk/")
        # Should be parseable as ISO
        parsed = datetime.fromisoformat(report["completed_at"].replace("Z", "+00:00"))
        assert parsed.tzinfo is not None


class TestBuildLoadReportSummary:
    def test_summary_counts_match_input(self, load_summary_success_and_failure):
        report = build_load_report(load_summary_success_and_failure, "processed/bulk/")
        s = report["summary"]
        assert s["total"] == 3
        assert s["success_count"] == 2
        assert s["failure_count"] == 1
        assert s["inserted"] == 2
        assert s["skipped"] == 1

    def test_summary_defaults_when_empty(self):
        empty = {"total": 0, "inserted": 0, "skipped": 0}
        report = build_load_report(empty, "any/prefix/")
        assert report["summary"]["total"] == 0
        assert report["summary"]["success_count"] == 0
        assert report["summary"]["failure_count"] == 0


class TestBuildLoadReportSuccessAndFailures:
    def test_success_items_passed_through(self, load_summary_success_and_failure):
        report = build_load_report(load_summary_success_and_failure, "processed/bulk/")
        assert report["success"]["count"] == 2
        assert len(report["success"]["items"]) == 2
        assert report["success"]["items"][0]["path"] == "processed/bulk/doc1.json"
        assert report["success"]["items"][0]["document_id"] == "leetcode_aaa"
        assert report["success"]["items"][0]["title"] == "Title One"

    def test_failures_read_errors_structure(self, load_summary_success_and_failure):
        report = build_load_report(load_summary_success_and_failure, "processed/bulk/")
        read_errors = report["failures"]["read_errors"]
        assert read_errors["count"] == 1
        assert read_errors["items"][0]["path"] == "processed/bulk/doc3.json"
        assert "missing" in read_errors["items"][0]["message"]

    def test_failures_insert_errors_structure(self):
        summary = {
            "total": 1,
            "inserted": 0,
            "skipped": 1,
            "errors": [],
            "success": [],
            "failed_reads": [],
            "failed_inserts": [
                {"document_id": "mid_xyz", "path": "p/doc.json", "title": "My Title", "message": "duplicate key"},
            ],
        }
        report = build_load_report(summary, "p/")
        insert_errors = report["failures"]["insert_errors"]
        assert insert_errors["count"] == 1
        assert insert_errors["items"][0]["document_id"] == "mid_xyz"
        assert insert_errors["items"][0]["title"] == "My Title"
        assert insert_errors["items"][0]["message"] == "duplicate key"
