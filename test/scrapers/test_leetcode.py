"""
Pytest suite for the LeetCode scraper.
Run with: pytest tests/scrapers/test_leetcode.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, call
import requests

from src.scrapers.leetcode import LeetCodeScraper
from src.scrapers.configs.leetcode import LeetCodeScraperConfigs


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=LeetCodeScraperConfigs)
    cfg.SCRAPE_TYPE = "bulk"
    cfg.DELAY_SECONDS = 0
    cfg.DETAIL_DELAY_SECONDS = 0
    cfg.BULK_MAX_POSTS = 100
    cfg.INCREMENTAL_MAX_POSTS = 10
    cfg.PAGE_SIZE = 10
    cfg.GRAPHQL_URL = "https://leetcode.com/graphql"
    cfg.USER_AGENT = "TestAgent/1.0"
    cfg.TARGET_TAGS = ["interview"]
    cfg.LIST_QUERY = "query {}"
    cfg.DETAIL_QUERY = "query {}"
    cfg.COMMENTS_QUERY = "query {}"
    cfg.MANIFESTS_PREFIX = "manifests"
    cfg.KNOWN_COMPANIES = ["Google", "Amazon", "Microsoft", "Meta", "Apple"]
    cfg.SKIP_TAGS = ["interview", "leetcode"]
    cfg.get_batch_id.return_value = "bulk_20240101"
    cfg.get_raw_prefix.return_value = "raw/bulk_20240101"
    cfg.get_today_str.return_value = "2024-01-01"
    return cfg


@pytest.fixture
def storage():
    s = MagicMock()
    s.file_exists.return_value = False
    return s


@pytest.fixture
def scraper(mock_config, storage):
    return LeetCodeScraper(scrape_type="bulk", config=mock_config, storage=storage)


# ── Constructor ───────────────────────────────────────────────────────────────

class TestLeetCodeScraperInit:
    def test_raises_without_storage(self, mock_config):
        with pytest.raises(ValueError, match="StorageBackend"):
            LeetCodeScraper(scrape_type="bulk", config=mock_config, storage=None)

    def test_uses_config_scrape_type_when_not_provided(self, mock_config, storage):
        mock_config.SCRAPE_TYPE = "incremental"
        s = LeetCodeScraper(config=mock_config, storage=storage)
        assert s.scrape_type == "incremental"

    def test_fetch_comments_defaults_false(self, mock_config, storage):
        s = LeetCodeScraper(scrape_type="bulk", config=mock_config, storage=storage)
        assert s.fetch_comments is False

    def test_fetch_comments_can_be_enabled(self, mock_config, storage):
        s = LeetCodeScraper(scrape_type="bulk", config=mock_config, storage=storage, fetch_comments=True)
        assert s.fetch_comments is True

    def test_stats_initialized_to_zero(self, scraper):
        assert scraper.stats["files_collected"] == 0
        assert scraper.stats["errors"] == 0
        assert scraper.stats["posts_listed"] == 0
        assert scraper.stats["pages_fetched"] == 0
        assert scraper.stats["error_ids"] == []


# ── _clean_content ────────────────────────────────────────────────────────────

class TestCleanContent:
    def test_strips_html_tags(self, scraper):
        result = scraper._clean_content("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert "Hello" in result
        assert "world" in result

    def test_collapses_multiple_newlines(self, scraper):
        result = scraper._clean_content("Line1\n\n\n\nLine2")
        assert "\n\n\n" not in result

    def test_collapses_extra_whitespace(self, scraper):
        result = scraper._clean_content("word1   word2\t\tword3")
        assert "  " not in result

    def test_returns_empty_string_for_none(self, scraper):
        assert scraper._clean_content(None) == ""

    def test_returns_empty_string_for_empty(self, scraper):
        assert scraper._clean_content("") == ""

    def test_strips_leading_trailing_whitespace(self, scraper):
        result = scraper._clean_content("  hello world  ")
        assert result == "hello world"


# ── _extract_company_from_tags ────────────────────────────────────────────────

class TestExtractCompanyFromTags:
    def test_extracts_company_type_tag(self, scraper):
        tags = [{"tagType": "COMPANY", "name": "Google", "slug": "google"}]
        assert scraper._extract_company_from_tags(tags) == "Google"

    def test_falls_back_to_known_company_slug(self, scraper):
        tags = [{"tagType": "TOPIC", "name": "Amazon", "slug": "amazon"}]
        assert scraper._extract_company_from_tags(tags) == "Amazon"

    def test_returns_none_for_empty_tags(self, scraper):
        assert scraper._extract_company_from_tags([]) is None

    def test_skips_skip_tags(self, scraper):
        tags = [{"tagType": "TOPIC", "name": "interview", "slug": "interview"}]
        assert scraper._extract_company_from_tags(tags) is None

    def test_company_type_takes_priority_over_slug_match(self, scraper):
        tags = [
            {"tagType": "COMPANY", "name": "Meta", "slug": "meta"},
            {"tagType": "TOPIC", "name": "Amazon", "slug": "amazon"},
        ]
        assert scraper._extract_company_from_tags(tags) == "Meta"

    def test_returns_none_when_no_match(self, scraper):
        tags = [{"tagType": "TOPIC", "name": "dynamic-programming", "slug": "dynamic-programming"}]
        assert scraper._extract_company_from_tags(tags) is None


# ── _extract_company_from_title ───────────────────────────────────────────────

class TestExtractCompanyFromTitle:
    def test_extracts_known_company(self, scraper):
        assert scraper._extract_company_from_title("Google SWE Interview Experience 2024") == "Google"

    def test_case_insensitive(self, scraper):
        assert scraper._extract_company_from_title("amazon onsite interview round 3") == "Amazon"

    def test_returns_none_for_unknown_company(self, scraper):
        assert scraper._extract_company_from_title("Some random startup interview") is None

    def test_returns_none_for_empty_title(self, scraper):
        assert scraper._extract_company_from_title("") is None


# ── _graphql_request ──────────────────────────────────────────────────────────

class TestGraphqlRequest:
    def _mock_response(self, json_data=None, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.raise_for_status = MagicMock()
        return resp

    def test_returns_data_on_success(self, scraper):
        resp = self._mock_response({"data": {"posts": []}})
        scraper.session.post = MagicMock(return_value=resp)
        result = scraper._graphql_request("op", "query {}", {})
        assert result == {"posts": []}

    def test_returns_none_on_graphql_errors(self, scraper):
        resp = self._mock_response({"errors": [{"message": "oops"}]})
        scraper.session.post = MagicMock(return_value=resp)
        result = scraper._graphql_request("op", "query {}", {})
        assert result is None

    def test_returns_none_on_timeout(self, scraper):
        scraper.session.post = MagicMock(side_effect=requests.exceptions.Timeout)
        result = scraper._graphql_request("op", "query {}", {})
        assert result is None
        assert scraper.stats["errors"] == 1

    def test_returns_none_on_request_exception(self, scraper):
        scraper.session.post = MagicMock(side_effect=requests.RequestException("error"))
        result = scraper._graphql_request("op", "query {}", {})
        assert result is None
        assert scraper.stats["errors"] == 1

    def test_retries_on_429(self, scraper):
        resp_429 = self._mock_response(status_code=429)
        resp_429.raise_for_status = MagicMock()
        resp_ok = self._mock_response({"data": {"result": "ok"}})
        scraper.session.post = MagicMock(side_effect=[resp_429, resp_ok])
        with patch("time.sleep"):
            result = scraper._graphql_request("op", "query {}", {})
        assert scraper.session.post.call_count == 2


# ── _parse_article ────────────────────────────────────────────────────────────

class TestParseArticle:
    def _make_article(self, **overrides):
        base = {
            "topicId": "12345",
            "slug": "google-swe-interview-2024",
            "title": "Google SWE Interview 2024",
            "content": "<p>Round 1 was a coding round with two problems.</p>",
            "createdAt": "2024-03-01T00:00:00Z",
            "updatedAt": "2024-03-02T00:00:00Z",
            "hitCount": 500,
            "reactions": [],
        }
        base.update(overrides)
        return base

    def _make_list_meta(self, **overrides):
        base = {
            "topicId": "12345",
            "title": "Google SWE Interview 2024",
            "slug": "google-swe-interview-2024",
            "tags": [],
            "isAnonymous": False,
            "topic": {"topLevelCommentCount": 0},
        }
        base.update(overrides)
        return base

    def test_returns_none_for_short_content(self, scraper):
        doc = scraper._parse_article(self._make_article(content="<p>Too short.</p>"), self._make_list_meta())
        assert doc is None


# ── _fetch_post_list ──────────────────────────────────────────────────────────

class TestFetchPostList:
    def _make_page(self, posts, has_next=False, total=None):
        edges = [{"node": p} for p in posts]
        return {
            "ugcArticleDiscussionArticles": {
                "edges": edges,
                "pageInfo": {"hasNextPage": has_next},
                "totalNum": total or len(posts),
            }
        }

    def test_returns_posts_from_single_page(self, scraper):
        posts = [{"topicId": str(i), "title": f"Post {i}", "slug": f"post-{i}"} for i in range(3)]
        scraper._graphql_request = MagicMock(return_value=self._make_page(posts))
        result = scraper._fetch_post_list()
        assert len(result) == 3

    def test_paginates_when_has_next(self, scraper):
        page1 = [{"topicId": str(i), "title": f"P{i}", "slug": f"p{i}"} for i in range(5)]
        page2 = [{"topicId": str(i), "title": f"P{i}", "slug": f"p{i}"} for i in range(5, 8)]
        scraper._graphql_request = MagicMock(side_effect=[
            self._make_page(page1, has_next=True, total=8),
            self._make_page(page2, has_next=False, total=8),
        ])
        result = scraper._fetch_post_list()
        assert len(result) == 8

    def test_stops_at_max_posts(self, scraper):
        scraper.config.BULK_MAX_POSTS = 5
        posts = [{"topicId": str(i), "title": f"P{i}", "slug": f"p{i}"} for i in range(10)]
        scraper._graphql_request = MagicMock(return_value=self._make_page(posts, has_next=True, total=100))
        result = scraper._fetch_post_list()
        assert len(result) == 5

    def test_returns_empty_list_when_no_posts(self, scraper):
        scraper._graphql_request = MagicMock(return_value=self._make_page([]))
        result = scraper._fetch_post_list()
        assert result == []

    def test_breaks_on_graphql_failure(self, scraper):
        scraper._graphql_request = MagicMock(return_value=None)
        result = scraper._fetch_post_list()
        assert result == []

    def test_updates_posts_listed_stat(self, scraper):
        posts = [{"topicId": str(i), "title": f"P{i}", "slug": f"p{i}"} for i in range(4)]
        scraper._graphql_request = MagicMock(return_value=self._make_page(posts))
        scraper._fetch_post_list()
        assert scraper.stats["posts_listed"] == 4


# ── _scrape_articles ──────────────────────────────────────────────────────────

class TestScrapeArticles:
    def _make_post(self, topic_id="1", title="Google Interview", slug="google-interview"):
        return {"topicId": topic_id, "title": title, "slug": slug, "tags": [], "isAnonymous": False}

    def _make_detail_response(self, content="Round 1: coding. Round 2: system design. Long content here."):
        return {
            "ugcArticleDiscussionArticle": {
                "topicId": "1",
                "slug": "google-interview",
                "title": "Google Interview",
                "content": content,
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-02T00:00:00Z",
                "hitCount": 100,
                "reactions": [],
            }
        }

    def test_skips_already_scraped_post(self, scraper, storage):
        storage.file_exists.return_value = True
        docs = scraper._scrape_articles([self._make_post()])
        assert docs == []
        assert scraper.stats["files_collected"] == 0

    def test_saves_new_document(self, scraper, storage):
        storage.file_exists.return_value = False
        scraper._graphql_request = MagicMock(return_value=self._make_detail_response())
        docs = scraper._scrape_articles([self._make_post()])
        assert len(docs) == 1
        assert scraper.stats["files_collected"] == 1
        storage.write_json.assert_called_once()

    def test_skips_post_without_topic_id(self, scraper):
        docs = scraper._scrape_articles([{"topicId": "", "title": "No ID", "slug": "no-id"}])
        assert docs == []

    def test_increments_error_on_graphql_failure(self, scraper, storage):
        storage.file_exists.return_value = False
        scraper._graphql_request = MagicMock(return_value=None)
        scraper._scrape_articles([self._make_post()])
        assert "1" in scraper.stats["error_ids"]

    def test_increments_error_on_empty_content(self, scraper, storage):
        storage.file_exists.return_value = False
        scraper._graphql_request = MagicMock(return_value={
            "ugcArticleDiscussionArticle": {"content": "", "topicId": "1"}
        })
        scraper._scrape_articles([self._make_post()])
        assert scraper.stats["errors"] == 1

    def test_fetches_comments_when_enabled(self, scraper, storage):
        scraper.fetch_comments = True
        storage.file_exists.return_value = False
        post = self._make_post()
        post["topic"] = {"topLevelCommentCount": 2}
        scraper._graphql_request = MagicMock(return_value=self._make_detail_response())
        scraper._fetch_post_comments = MagicMock(return_value=[{"id": 1}])
        with patch("time.sleep"):
            scraper._scrape_articles([post])
        scraper._fetch_post_comments.assert_called_once()

    def test_does_not_fetch_comments_when_disabled(self, scraper, storage):
        scraper.fetch_comments = False
        storage.file_exists.return_value = False
        post = self._make_post()
        post["topic"] = {"topLevelCommentCount": 5}
        scraper._graphql_request = MagicMock(return_value=self._make_detail_response())
        scraper._fetch_post_comments = MagicMock()
        scraper._scrape_articles([post])
        scraper._fetch_post_comments.assert_not_called()


# ── _fetch_post_comments ──────────────────────────────────────────────────────

class TestFetchPostComments:
    def _comment_response(self, comments, total):
        return {
            "topicComments": {
                "data": comments,
                "totalNum": total,
            }
        }

    def _make_comment(self, cid, content="Great post!", hidden=False):
        return {
            "id": cid,
            "post": {
                "content": content,
                "creationDate": "2024-01-01",
                "voteCount": 3,
                "anonymous": False,
                "isHidden": hidden,
            },
            "numChildren": 0,
        }

    def test_returns_visible_comments(self, scraper):
        comments = [self._make_comment(1), self._make_comment(2)]
        scraper._graphql_request = MagicMock(return_value=self._comment_response(comments, 2))
        result = scraper._fetch_post_comments(12345)
        assert len(result) == 2

    def test_stops_when_all_comments_fetched(self, scraper):
        comments = [self._make_comment(1)]
        scraper._graphql_request = MagicMock(return_value=self._comment_response(comments, 1))
        scraper._fetch_post_comments(12345)
        assert scraper._graphql_request.call_count == 1

    def test_returns_empty_on_graphql_failure(self, scraper):
        scraper._graphql_request = MagicMock(return_value=None)
        result = scraper._fetch_post_comments(12345)
        assert result == []


# ── _create_manifest ──────────────────────────────────────────────────────────

class TestLeetCodeCreateManifest:
    def test_saves_manifest_to_storage(self, scraper):
        with patch("src.scrapers.leetcode.Manifest") as MockManifest:
            mock_inst = MagicMock()
            MockManifest.return_value = mock_inst
            scraper._create_manifest([], "2024-01-01T00:00:00Z")
            mock_inst.save.assert_called_once()

    def test_manifest_includes_correct_stats(self, scraper):
        scraper.stats["files_collected"] = 7
        scraper.stats["errors"] = 2
        with patch("src.scrapers.leetcode.Manifest") as MockManifest:
            mock_inst = MagicMock()
            MockManifest.return_value = mock_inst
            scraper._create_manifest([], "2024-01-01T00:00:00Z")
            sources = MockManifest.call_args[1]["sources"]
            assert sources["leetcode"]["files_collected"] == 7
            assert sources["leetcode"]["errors"] == 2