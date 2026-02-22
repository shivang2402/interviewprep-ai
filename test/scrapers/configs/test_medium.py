"""
Pytest suite for MediumScraperConfigs.
Run with: pytest tests/scrapers/configs/test_medium.py -v
"""

import pytest
from datetime import date
from unittest.mock import patch

from src.scrapers.configs.medium import MediumScraperConfigs


# ── Static Attributes ─────────────────────────────────────────────────────────

class TestMediumStaticAttributes:
    def test_sitemap_index_url_is_valid(self):
        assert MediumScraperConfigs.SITEMAP_INDEX_URL.startswith("https://")
        assert "medium.com" in MediumScraperConfigs.SITEMAP_INDEX_URL

    def test_sitemap_filter_pattern_is_non_empty(self):
        assert isinstance(MediumScraperConfigs.SITEMAP_FILTER_PATTERN, str)
        assert len(MediumScraperConfigs.SITEMAP_FILTER_PATTERN) > 0

    def test_interview_url_keyword_is_non_empty(self):
        assert isinstance(MediumScraperConfigs.INTERVIEW_URL_KEYWORD, str)
        assert len(MediumScraperConfigs.INTERVIEW_URL_KEYWORD) > 0

    def test_scrape_type_is_valid(self):
        assert MediumScraperConfigs.SCRAPE_TYPE in ("bulk", "incremental")

    def test_bulk_start_date_is_valid_iso_date(self):
        parsed = date.fromisoformat(MediumScraperConfigs.BULK_START_DATE)
        assert isinstance(parsed, date)

    def test_raw_prefix_is_non_empty(self):
        assert isinstance(MediumScraperConfigs.RAW_PREFIX, str)
        assert len(MediumScraperConfigs.RAW_PREFIX) > 0

    def test_manifests_prefix_is_non_empty(self):
        assert isinstance(MediumScraperConfigs.MANIFESTS_PREFIX, str)
        assert len(MediumScraperConfigs.MANIFESTS_PREFIX) > 0

    def test_user_agent_is_non_empty_string(self):
        assert isinstance(MediumScraperConfigs.USER_AGENT, str)
        assert len(MediumScraperConfigs.USER_AGENT) > 0

    def test_max_sitemaps_is_none_or_positive_int(self):
        v = MediumScraperConfigs.MAX_SITEMAPS
        assert v is None or (isinstance(v, int) and v > 0)


# ── Delay Settings ────────────────────────────────────────────────────────────

class TestDelaySettings:
    def test_fetch_delay_min_is_non_negative(self):
        assert MediumScraperConfigs.FETCH_DELAY_MIN >= 0

    def test_fetch_delay_max_greater_than_or_equal_min(self):
        assert MediumScraperConfigs.FETCH_DELAY_MAX >= MediumScraperConfigs.FETCH_DELAY_MIN

    def test_between_articles_delay_min_is_non_negative(self):
        assert MediumScraperConfigs.BETWEEN_ARTICLES_DELAY_MIN >= 0

    def test_between_articles_delay_max_gte_min(self):
        assert (MediumScraperConfigs.BETWEEN_ARTICLES_DELAY_MAX
                >= MediumScraperConfigs.BETWEEN_ARTICLES_DELAY_MIN)

    def test_post_load_delay_min_is_non_negative(self):
        assert MediumScraperConfigs.POST_LOAD_DELAY_MIN >= 0

    def test_post_load_delay_max_gte_min(self):
        assert (MediumScraperConfigs.POST_LOAD_DELAY_MAX
                >= MediumScraperConfigs.POST_LOAD_DELAY_MIN)

    def test_rate_limit_sleep_is_positive(self):
        assert MediumScraperConfigs.RATE_LIMIT_SLEEP > 0


# ── Browser Settings ──────────────────────────────────────────────────────────

class TestBrowserSettings:
    def test_viewport_width_is_positive(self):
        assert MediumScraperConfigs.VIEWPORT_WIDTH > 0

    def test_viewport_height_is_positive(self):
        assert MediumScraperConfigs.VIEWPORT_HEIGHT > 0

    def test_locale_is_non_empty_string(self):
        assert isinstance(MediumScraperConfigs.LOCALE, str)
        assert len(MediumScraperConfigs.LOCALE) > 0

    def test_timezone_id_is_non_empty_string(self):
        assert isinstance(MediumScraperConfigs.TIMEZONE_ID, str)
        assert len(MediumScraperConfigs.TIMEZONE_ID) > 0

    def test_locale_format(self):
        # Expect IETF language tag format e.g. "en-US"
        assert "-" in MediumScraperConfigs.LOCALE

    def test_timezone_contains_slash(self):
        # Expect IANA timezone format e.g. "America/New_York"
        assert "/" in MediumScraperConfigs.TIMEZONE_ID


# ── Content Validation Settings ───────────────────────────────────────────────

class TestContentValidationSettings:
    def test_min_content_length_is_positive(self):
        assert MediumScraperConfigs.MIN_CONTENT_LENGTH > 0

    def test_min_meaningful_paragraph_length_is_positive(self):
        assert MediumScraperConfigs.MIN_MEANINGFUL_PARAGRAPH_LENGTH > 0

    def test_min_meaningful_paragraph_count_is_positive(self):
        assert MediumScraperConfigs.MIN_MEANINGFUL_PARAGRAPH_COUNT > 0

    def test_min_content_length_is_int(self):
        assert isinstance(MediumScraperConfigs.MIN_CONTENT_LENGTH, int)

    def test_min_paragraph_length_is_int(self):
        assert isinstance(MediumScraperConfigs.MIN_MEANINGFUL_PARAGRAPH_LENGTH, int)

    def test_min_paragraph_count_is_int(self):
        assert isinstance(MediumScraperConfigs.MIN_MEANINGFUL_PARAGRAPH_COUNT, int)


# ── Timeout Settings ──────────────────────────────────────────────────────────

class TestTimeoutSettings:
    def test_page_timeout_is_positive(self):
        assert MediumScraperConfigs.PAGE_TIMEOUT > 0

    def test_download_timeout_is_positive(self):
        assert MediumScraperConfigs.DOWNLOAD_TIMEOUT > 0

    def test_page_timeout_is_int(self):
        assert isinstance(MediumScraperConfigs.PAGE_TIMEOUT, int)

    def test_download_timeout_is_int(self):
        assert isinstance(MediumScraperConfigs.DOWNLOAD_TIMEOUT, int)

    def test_page_timeout_in_milliseconds(self):
        # Reasonable millisecond range: 5s–120s
        assert 5_000 <= MediumScraperConfigs.PAGE_TIMEOUT <= 120_000

    def test_download_timeout_less_than_page_timeout(self):
        # Download timeout should not exceed the page load timeout
        assert MediumScraperConfigs.DOWNLOAD_TIMEOUT <= MediumScraperConfigs.PAGE_TIMEOUT


# ── get_today_str ─────────────────────────────────────────────────────────────

class TestGetTodayStr:
    def test_returns_string(self):
        assert isinstance(MediumScraperConfigs.get_today_str(), str)

    def test_returns_valid_iso_date(self):
        parsed = date.fromisoformat(MediumScraperConfigs.get_today_str())
        assert isinstance(parsed, date)

    def test_matches_todays_date(self):
        assert MediumScraperConfigs.get_today_str() == date.today().isoformat()


# ── get_batch_id ──────────────────────────────────────────────────────────────

class TestGetBatchId:
    FIXED_DATE = "2025-02-14"

    def test_bulk_produces_bulk_suffix(self):
        with patch.object(MediumScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert MediumScraperConfigs.get_batch_id("bulk").endswith("_bulk")

    def test_incremental_produces_weekly_suffix(self):
        with patch.object(MediumScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert MediumScraperConfigs.get_batch_id("incremental").endswith("_weekly")

    def test_unknown_type_produces_weekly_suffix(self):
        with patch.object(MediumScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert MediumScraperConfigs.get_batch_id("anything_else").endswith("_weekly")

    def test_batch_id_starts_with_date(self):
        with patch.object(MediumScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert MediumScraperConfigs.get_batch_id("bulk").startswith(self.FIXED_DATE)

    def test_bulk_batch_id_exact_format(self):
        with patch.object(MediumScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert MediumScraperConfigs.get_batch_id("bulk") == f"{self.FIXED_DATE}_bulk"

    def test_incremental_batch_id_exact_format(self):
        with patch.object(MediumScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert MediumScraperConfigs.get_batch_id("incremental") == f"{self.FIXED_DATE}_weekly"


# ── get_raw_prefix ────────────────────────────────────────────────────────────

class TestGetRawPrefix:
    def test_starts_with_raw_constant(self):
        prefix = MediumScraperConfigs.get_raw_prefix("2025-02-14_bulk")
        assert prefix.startswith(MediumScraperConfigs.RAW_PREFIX)

    def test_includes_batch_id(self):
        batch_id = "2025-02-14_bulk"
        assert batch_id in MediumScraperConfigs.get_raw_prefix(batch_id)

    def test_ends_with_medium(self):
        assert MediumScraperConfigs.get_raw_prefix("2025-02-14_bulk").endswith("/medium")

    def test_bulk_prefix_exact_format(self):
        with patch.object(MediumScraperConfigs, "get_today_str", return_value="2025-02-14"):
            batch_id = MediumScraperConfigs.get_batch_id("bulk")
            prefix = MediumScraperConfigs.get_raw_prefix(batch_id)
        assert prefix == "raw/2025-02-14_bulk/medium"

    def test_incremental_prefix_exact_format(self):
        with patch.object(MediumScraperConfigs, "get_today_str", return_value="2025-02-14"):
            batch_id = MediumScraperConfigs.get_batch_id("incremental")
            prefix = MediumScraperConfigs.get_raw_prefix(batch_id)
        assert prefix == "raw/2025-02-14_weekly/medium"

    def test_no_leading_slash(self):
        assert not MediumScraperConfigs.get_raw_prefix("2025-02-14_bulk").startswith("/")