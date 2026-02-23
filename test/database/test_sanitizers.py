"""
Tests for src/database/sanitizers.py

Covers db_platform() and db_enum() used to map Python model values to DB enums.
"""

import pytest

from src.database.sanitizers import (
    db_platform,
    db_enum,
    PLATFORM_TO_DB,
    DB_EXPERIENCE_VALID,
    DB_OUTCOME_VALID,
    DB_DIFFICULTY_VALID,
    DB_INTERVIEW_TYPE_VALID,
)


class TestDbPlatform:
    def test_leetcode_passthrough(self):
        assert db_platform("leetcode") == "leetcode"

    def test_geeksforgeeks_maps_to_gfg(self):
        assert db_platform("geeksforgeeks") == "gfg"

    def test_medium_passthrough(self):
        assert db_platform("medium") == "medium"

    def test_unknown_platform_passthrough(self):
        assert db_platform("unknown_platform") == "unknown_platform"

    def test_platform_to_db_has_expected_keys(self):
        assert "leetcode" in PLATFORM_TO_DB
        assert "geeksforgeeks" in PLATFORM_TO_DB
        assert PLATFORM_TO_DB["geeksforgeeks"] == "gfg"


class TestDbEnum:
    def test_none_returns_none(self):
        assert db_enum(None, {"a", "b"}) is None

    def test_valid_value_returned(self):
        assert db_enum("mid", DB_EXPERIENCE_VALID) == "mid"
        assert db_enum("offer", DB_OUTCOME_VALID) == "offer"
        assert db_enum("medium", DB_DIFFICULTY_VALID) == "medium"
        assert db_enum("onsite", DB_INTERVIEW_TYPE_VALID) == "onsite"

    def test_invalid_value_returns_none(self):
        assert db_enum("unknown", DB_EXPERIENCE_VALID) is None
        assert db_enum("unknown", DB_OUTCOME_VALID) is None
        assert db_enum("executive", DB_EXPERIENCE_VALID) is None

    def test_empty_valid_set_returns_none_for_any_value(self):
        assert db_enum("anything", set()) is None
