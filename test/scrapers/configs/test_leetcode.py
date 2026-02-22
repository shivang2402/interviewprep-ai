"""
Pytest suite for LeetCodeScraperConfigs.
Run with: pytest tests/scrapers/configs/test_leetcode.py -v
"""

import pytest
from datetime import date
from unittest.mock import patch

from src.scrapers.configs.leetcode import LeetCodeScraperConfigs


# ── Static Attributes ─────────────────────────────────────────────────────────

class TestLeetCodeStaticAttributes:
    def test_graphql_url_is_valid(self):
        assert LeetCodeScraperConfigs.GRAPHQL_URL.startswith("https://")
        assert "leetcode.com" in LeetCodeScraperConfigs.GRAPHQL_URL

    def test_target_tags_is_non_empty_list(self):
        assert isinstance(LeetCodeScraperConfigs.TARGET_TAGS, list)
        assert len(LeetCodeScraperConfigs.TARGET_TAGS) > 0

    def test_target_tags_contains_interview(self):
        assert "interview" in LeetCodeScraperConfigs.TARGET_TAGS

    def test_scrape_type_is_valid(self):
        assert LeetCodeScraperConfigs.SCRAPE_TYPE in ("bulk", "incremental")

    def test_bulk_max_posts_is_positive_or_inf(self):
        v = LeetCodeScraperConfigs.BULK_MAX_POSTS
        assert v == float('inf') or v > 0

    def test_incremental_max_posts_is_positive_int(self):
        assert isinstance(LeetCodeScraperConfigs.INCREMENTAL_MAX_POSTS, int)
        assert LeetCodeScraperConfigs.INCREMENTAL_MAX_POSTS > 0

    def test_page_size_is_positive_int(self):
        assert isinstance(LeetCodeScraperConfigs.PAGE_SIZE, int)
        assert LeetCodeScraperConfigs.PAGE_SIZE > 0

    def test_delay_seconds_is_non_negative(self):
        assert LeetCodeScraperConfigs.DELAY_SECONDS >= 0

    def test_detail_delay_seconds_is_non_negative(self):
        assert LeetCodeScraperConfigs.DETAIL_DELAY_SECONDS >= 0

    def test_user_agent_is_non_empty_string(self):
        assert isinstance(LeetCodeScraperConfigs.USER_AGENT, str)
        assert len(LeetCodeScraperConfigs.USER_AGENT) > 0

    def test_raw_prefix_is_non_empty(self):
        assert isinstance(LeetCodeScraperConfigs.RAW_PREFIX, str)
        assert len(LeetCodeScraperConfigs.RAW_PREFIX) > 0

    def test_manifests_prefix_is_non_empty(self):
        assert isinstance(LeetCodeScraperConfigs.MANIFESTS_PREFIX, str)
        assert len(LeetCodeScraperConfigs.MANIFESTS_PREFIX) > 0


# ── Skip Tags ─────────────────────────────────────────────────────────────────

class TestSkipTags:
    def test_skip_tags_is_frozenset(self):
        assert isinstance(LeetCodeScraperConfigs.SKIP_TAGS, frozenset)

    def test_skip_tags_is_non_empty(self):
        assert len(LeetCodeScraperConfigs.SKIP_TAGS) > 0

    def test_interview_in_skip_tags(self):
        assert "interview" in LeetCodeScraperConfigs.SKIP_TAGS

    @pytest.mark.parametrize("tag", [
        "interview", "interview-experience", "compensation",
        "system-design", "behavioral", "online-assessment",
    ])
    def test_common_noise_tags_are_skipped(self, tag):
        assert tag in LeetCodeScraperConfigs.SKIP_TAGS

    def test_skip_tags_are_lowercase(self):
        for tag in LeetCodeScraperConfigs.SKIP_TAGS:
            assert tag == tag.lower(), f"Expected lowercase, got: {tag}"

    def test_skip_tags_are_strings(self):
        assert all(isinstance(t, str) for t in LeetCodeScraperConfigs.SKIP_TAGS)


# ── Known Companies ───────────────────────────────────────────────────────────

class TestKnownCompanies:
    def test_known_companies_is_list(self):
        assert isinstance(LeetCodeScraperConfigs.KNOWN_COMPANIES, list)

    def test_known_companies_is_non_empty(self):
        assert len(LeetCodeScraperConfigs.KNOWN_COMPANIES) > 0

    @pytest.mark.parametrize("company", [
        "Google", "Amazon", "Meta", "Microsoft", "Apple", "Netflix",
    ])
    def test_faang_companies_present(self, company):
        assert company in LeetCodeScraperConfigs.KNOWN_COMPANIES

    def test_no_duplicate_companies(self):
        companies = LeetCodeScraperConfigs.KNOWN_COMPANIES
        assert len(companies) == len(set(companies))

    def test_companies_are_strings(self):
        assert all(isinstance(c, str) for c in LeetCodeScraperConfigs.KNOWN_COMPANIES)

    def test_companies_are_non_empty_strings(self):
        assert all(len(c) > 0 for c in LeetCodeScraperConfigs.KNOWN_COMPANIES)

    def test_no_company_matches_skip_tag(self):
        """No company name should be accidentally in SKIP_TAGS (case-insensitive)."""
        skip_lower = LeetCodeScraperConfigs.SKIP_TAGS
        for company in LeetCodeScraperConfigs.KNOWN_COMPANIES:
            assert company.lower() not in skip_lower, (
                f"Company '{company}' found in SKIP_TAGS — would break company extraction."
            )


# ── GraphQL Queries ───────────────────────────────────────────────────────────

class TestGraphQLQueries:
    def test_list_query_is_non_empty_string(self):
        assert isinstance(LeetCodeScraperConfigs.LIST_QUERY, str)
        assert len(LeetCodeScraperConfigs.LIST_QUERY.strip()) > 0

    def test_detail_query_is_non_empty_string(self):
        assert isinstance(LeetCodeScraperConfigs.DETAIL_QUERY, str)
        assert len(LeetCodeScraperConfigs.DETAIL_QUERY.strip()) > 0

    def test_comments_query_is_non_empty_string(self):
        assert isinstance(LeetCodeScraperConfigs.COMMENTS_QUERY, str)
        assert len(LeetCodeScraperConfigs.COMMENTS_QUERY.strip()) > 0

    def test_list_query_declares_operation_name(self):
        assert "discussPostItems" in LeetCodeScraperConfigs.LIST_QUERY

    def test_detail_query_declares_operation_name(self):
        assert "discussPostDetail" in LeetCodeScraperConfigs.DETAIL_QUERY

    def test_comments_query_declares_operation_name(self):
        assert "questionDiscussComments" in LeetCodeScraperConfigs.COMMENTS_QUERY

    def test_list_query_requests_topic_id(self):
        assert "topicId" in LeetCodeScraperConfigs.LIST_QUERY

    def test_detail_query_requests_content(self):
        assert "content" in LeetCodeScraperConfigs.DETAIL_QUERY

    def test_list_query_requests_pagination_fields(self):
        query = LeetCodeScraperConfigs.LIST_QUERY
        assert "hasNextPage" in query
        assert "totalNum" in query

    def test_detail_query_requests_tags(self):
        assert "tags" in LeetCodeScraperConfigs.DETAIL_QUERY

    def test_list_query_has_skip_and_first_variables(self):
        query = LeetCodeScraperConfigs.LIST_QUERY
        assert "$skip" in query
        assert "$first" in query


# ── get_today_str ─────────────────────────────────────────────────────────────

class TestGetTodayStr:
    def test_returns_string(self):
        assert isinstance(LeetCodeScraperConfigs.get_today_str(), str)

    def test_returns_valid_iso_date(self):
        parsed = date.fromisoformat(LeetCodeScraperConfigs.get_today_str())
        assert isinstance(parsed, date)

    def test_matches_todays_date(self):
        assert LeetCodeScraperConfigs.get_today_str() == date.today().isoformat()


# ── get_batch_id ──────────────────────────────────────────────────────────────

class TestGetBatchId:
    FIXED_DATE = "2024-09-20"

    def test_bulk_type_produces_bulk_suffix(self):
        with patch.object(LeetCodeScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert LeetCodeScraperConfigs.get_batch_id("bulk").endswith("_bulk")

    def test_incremental_type_produces_weekly_suffix(self):
        with patch.object(LeetCodeScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert LeetCodeScraperConfigs.get_batch_id("incremental").endswith("_weekly")

    def test_unknown_type_produces_weekly_suffix(self):
        with patch.object(LeetCodeScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert LeetCodeScraperConfigs.get_batch_id("unknown").endswith("_weekly")

    def test_batch_id_starts_with_date(self):
        with patch.object(LeetCodeScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert LeetCodeScraperConfigs.get_batch_id("bulk").startswith(self.FIXED_DATE)

    def test_bulk_batch_id_exact_format(self):
        with patch.object(LeetCodeScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert LeetCodeScraperConfigs.get_batch_id("bulk") == f"{self.FIXED_DATE}_bulk"

    def test_incremental_batch_id_exact_format(self):
        with patch.object(LeetCodeScraperConfigs, "get_today_str", return_value=self.FIXED_DATE):
            assert LeetCodeScraperConfigs.get_batch_id("incremental") == f"{self.FIXED_DATE}_weekly"


# ── get_raw_prefix ────────────────────────────────────────────────────────────

class TestGetRawPrefix:
    def test_starts_with_raw_constant(self):
        prefix = LeetCodeScraperConfigs.get_raw_prefix("2024-09-20_bulk")
        assert prefix.startswith(LeetCodeScraperConfigs.RAW_PREFIX)

    def test_includes_batch_id(self):
        batch_id = "2024-09-20_bulk"
        assert batch_id in LeetCodeScraperConfigs.get_raw_prefix(batch_id)

    def test_ends_with_leetcode(self):
        assert LeetCodeScraperConfigs.get_raw_prefix("2024-09-20_bulk").endswith("/leetcode")

    def test_bulk_prefix_exact_format(self):
        with patch.object(LeetCodeScraperConfigs, "get_today_str", return_value="2024-09-20"):
            batch_id = LeetCodeScraperConfigs.get_batch_id("bulk")
            prefix = LeetCodeScraperConfigs.get_raw_prefix(batch_id)
        assert prefix == "raw/2024-09-20_bulk/leetcode"

    def test_incremental_prefix_exact_format(self):
        with patch.object(LeetCodeScraperConfigs, "get_today_str", return_value="2024-09-20"):
            batch_id = LeetCodeScraperConfigs.get_batch_id("incremental")
            prefix = LeetCodeScraperConfigs.get_raw_prefix(batch_id)
        assert prefix == "raw/2024-09-20_weekly/leetcode"

    def test_no_leading_slash(self):
        assert not LeetCodeScraperConfigs.get_raw_prefix("2024-09-20_bulk").startswith("/")