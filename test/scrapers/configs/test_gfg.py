"""
Pytest suite for GFGScraperConfigs.
Run with: pytest tests/scrapers/configs/test_gfg.py -v
"""

import re
import pytest
from datetime import date
from unittest.mock import patch

from src.scrapers.configs.gfg import GFGScraperConfigs


# ── Static Attributes ─────────────────────────────────────────────────────────

class TestGFGStaticAttributes:
    def test_sitemap_index_url_is_valid(self):
        assert GFGScraperConfigs.SITEMAP_INDEX_URL.startswith("https://")
        assert "geeksforgeeks.org" in GFGScraperConfigs.SITEMAP_INDEX_URL

    def test_post_sitemap_prefix_is_valid(self):
        assert GFGScraperConfigs.POST_SITEMAP_PREFIX.startswith("https://")
        assert "geeksforgeeks.org" in GFGScraperConfigs.POST_SITEMAP_PREFIX

    def test_interview_url_pattern_is_non_empty_string(self):
        assert isinstance(GFGScraperConfigs.INTERVIEW_URL_PATTERN, str)
        assert len(GFGScraperConfigs.INTERVIEW_URL_PATTERN) > 0

    def test_scrape_type_is_bulk_or_incremental(self):
        assert GFGScraperConfigs.SCRAPE_TYPE in ("bulk", "incremental")

    def test_bulk_start_date_is_valid_iso_date(self):
        parsed = date.fromisoformat(GFGScraperConfigs.BULK_START_DATE)
        assert isinstance(parsed, date)

    def test_delay_seconds_is_positive(self):
        assert GFGScraperConfigs.DELAY_SECONDS > 0

    def test_user_agent_is_non_empty_string(self):
        assert isinstance(GFGScraperConfigs.USER_AGENT, str)
        assert len(GFGScraperConfigs.USER_AGENT) > 0

    def test_raw_prefix_is_non_empty(self):
        assert isinstance(GFGScraperConfigs.RAW_PREFIX, str)
        assert len(GFGScraperConfigs.RAW_PREFIX) > 0

    def test_manifests_prefix_is_non_empty(self):
        assert isinstance(GFGScraperConfigs.MANIFESTS_PREFIX, str)
        assert len(GFGScraperConfigs.MANIFESTS_PREFIX) > 0


# ── Interview URL Pattern ─────────────────────────────────────────────────────

class TestInterviewUrlPattern:
    PATTERN = re.compile(GFGScraperConfigs.INTERVIEW_URL_PATTERN)

    @pytest.mark.parametrize("url", [
        "https://www.geeksforgeeks.org/interview-experiences/amazon-interview-experience-2024/",
        "https://www.geeksforgeeks.org/interview-experiences/google-interview-sde1/",
        "https://www.geeksforgeeks.org/interview-experiences/microsoft-sde-interview/",
    ])
    def test_matches_valid_interview_urls(self, url):
        assert self.PATTERN.match(url), f"Expected match for: {url}"

    @pytest.mark.parametrize("url", [
        "https://www.geeksforgeeks.org/python-tutorial/",
        "https://www.geeksforgeeks.org/data-structures/",
        "https://www.geeksforgeeks.org/",
        "https://other-site.com/interview-experiences/google/",
    ])
    def test_does_not_match_non_interview_urls(self, url):
        assert not self.PATTERN.match(url), f"Expected no match for: {url}"

    def test_pattern_requires_interview_in_slug(self):
        url = "https://www.geeksforgeeks.org/interview-experiences/amazon-sde-experience/"
        # Slug does not contain "interview" — should not match per pattern
        assert not self.PATTERN.match(url)


# ── get_today_str ─────────────────────────────────────────────────────────────

class TestGetTodayStr:
    def test_returns_iso_format_string(self):
        result = GFGScraperConfigs.get_today_str()
        parsed = date.fromisoformat(result)
        assert isinstance(parsed, date)

    def test_matches_todays_date(self):
        result = GFGScraperConfigs.get_today_str()
        assert result == date.today().isoformat()

    def test_returns_string_type(self):
        assert isinstance(GFGScraperConfigs.get_today_str(), str)


# ── get_batch_id ──────────────────────────────────────────────────────────────

class TestGetBatchId:
    FIXED_DATE = "2024-06-15"

    def test_bulk_suffix_for_bulk_scrape_type(self):
        with patch.object(GFGScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            batch_id = GFGScraperConfigs.get_batch_id("bulk")
        assert batch_id.endswith("_bulk")

    def test_weekly_suffix_for_incremental_scrape_type(self):
        with patch.object(GFGScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            batch_id = GFGScraperConfigs.get_batch_id("incremental")
        assert batch_id.endswith("_weekly")

    def test_weekly_suffix_for_any_non_bulk_type(self):
        with patch.object(GFGScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            batch_id = GFGScraperConfigs.get_batch_id("other")
        assert batch_id.endswith("_weekly")

    def test_includes_todays_date_prefix(self):
        with patch.object(GFGScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            batch_id = GFGScraperConfigs.get_batch_id("bulk")
        assert batch_id.startswith(self.FIXED_DATE)

    def test_format_is_date_underscore_suffix(self):
        with patch.object(GFGScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            batch_id = GFGScraperConfigs.get_batch_id("bulk")
        assert batch_id == f"{self.FIXED_DATE}_bulk"


# ── get_raw_prefix ────────────────────────────────────────────────────────────

class TestGetRawPrefix:
    def test_starts_with_raw_prefix_constant(self):
        prefix = GFGScraperConfigs.get_raw_prefix("2024-06-15_bulk")
        assert prefix.startswith(GFGScraperConfigs.RAW_PREFIX)

    def test_includes_batch_id(self):
        batch_id = "2024-06-15_bulk"
        prefix = GFGScraperConfigs.get_raw_prefix(batch_id)
        assert batch_id in prefix

    def test_ends_with_gfg(self):
        prefix = GFGScraperConfigs.get_raw_prefix("2024-06-15_bulk")
        assert prefix.endswith("/gfg")

    def test_bulk_prefix_structure(self):
        with patch.object(GFGScraperConfigs, "get_today_str", return_value="2024-06-15"):
            batch_id = GFGScraperConfigs.get_batch_id("bulk")
            prefix = GFGScraperConfigs.get_raw_prefix(batch_id)
        assert prefix == "raw/2024-06-15_bulk/gfg"

    def test_incremental_prefix_structure(self):
        with patch.object(GFGScraperConfigs, "get_today_str", return_value="2024-06-15"):
            batch_id = GFGScraperConfigs.get_batch_id("incremental")
            prefix = GFGScraperConfigs.get_raw_prefix(batch_id)
        assert prefix == "raw/2024-06-15_weekly/gfg"

    def test_no_leading_slash(self):
        prefix = GFGScraperConfigs.get_raw_prefix("2024-06-15_bulk")
        assert not prefix.startswith("/")