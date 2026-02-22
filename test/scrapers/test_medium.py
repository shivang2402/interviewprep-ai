"""
Pytest suite for the Medium scraper.
Run with: pytest tests/scrapers/test_medium.py -v
"""

import json
import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

from src.scrapers.medium import MediumScraper, SitemapInfo, categorize_error
from src.scrapers.configs.medium import MediumScraperConfigs


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=MediumScraperConfigs)
    cfg.SCRAPE_TYPE = "bulk"
    cfg.BULK_START_DATE = "2023-01-01"
    cfg.SITEMAP_INDEX_URL = "https://medium.com/sitemap/sitemap.xml"
    cfg.SITEMAP_FILTER_PATTERN = "interview"
    cfg.INTERVIEW_URL_KEYWORD = "interview"
    cfg.USER_AGENT = "TestAgent/1.0"
    cfg.DOWNLOAD_TIMEOUT = 5000
    cfg.PAGE_TIMEOUT = 30000
    cfg.FETCH_DELAY_MIN = 0
    cfg.FETCH_DELAY_MAX = 0
    cfg.POST_LOAD_DELAY_MIN = 0
    cfg.POST_LOAD_DELAY_MAX = 0
    cfg.BETWEEN_ARTICLES_DELAY_MIN = 0
    cfg.BETWEEN_ARTICLES_DELAY_MAX = 0
    cfg.VIEWPORT_WIDTH = 1280
    cfg.VIEWPORT_HEIGHT = 720
    cfg.LOCALE = "en-US"
    cfg.TIMEZONE_ID = "America/New_York"
    cfg.RATE_LIMIT_SLEEP = 0
    cfg.MIN_CONTENT_LENGTH = 100
    cfg.MIN_MEANINGFUL_PARAGRAPH_LENGTH = 50
    cfg.MIN_MEANINGFUL_PARAGRAPH_COUNT = 3
    cfg.MAX_SITEMAPS = None
    cfg.MANIFESTS_PREFIX = "manifests"
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
def scraper(mock_config, storage, tmp_path):
    return MediumScraper(
        scrape_type="bulk",
        config=mock_config,
        storage=storage,
        log_dir=str(tmp_path),
    )


# ── SitemapInfo ───────────────────────────────────────────────────────────────

class TestMediumSitemapInfo:
    def test_lastmod_date_with_datetime(self):
        si = SitemapInfo(url="https://medium.com/sm.xml", lastmod="2024-05-10T12:00:00Z")
        assert si.lastmod_date() == date(2024, 5, 10)

    def test_lastmod_date_with_date_only(self):
        si = SitemapInfo(url="https://medium.com/sm.xml", lastmod="2024-05-10")
        assert si.lastmod_date() == date(2024, 5, 10)

    def test_lastmod_date_none_when_no_lastmod(self):
        si = SitemapInfo(url="https://medium.com/sm.xml", lastmod=None)
        assert si.lastmod_date() is None

    def test_lastmod_date_none_on_bad_format(self):
        si = SitemapInfo(url="https://medium.com/sm.xml", lastmod="garbage")
        assert si.lastmod_date() is None


# ── categorize_error ──────────────────────────────────────────────────────────

class TestCategorizeError:
    @pytest.mark.parametrize("error_type,expected_category", [
        ("HTTP_410_GONE",           "http_410_gone"),
        ("HTTP_404_NOT_FOUND",      "http_404_not_found"),
        ("HTTP_403_FORBIDDEN",      "http_403_forbidden"),
        ("HTTP_429_RATE_LIMITED",   "http_429_rate_limited"),
        ("TIMEOUT",                 "timeout"),
        ("CONNECTION_ERROR",        "connection_error"),
        ("HTTP_500_SERVER_ERROR",   "http_5xx_server_error"),
        ("SOMETHING_ELSE",          "other"),
    ])
    def test_categories(self, error_type, expected_category):
        category, _ = categorize_error(error_type)
        assert category == expected_category

    def test_returns_tuple_of_two(self):
        result = categorize_error("HTTP_404_NOT_FOUND")
        assert isinstance(result, tuple)
        assert len(result) == 2


# ── Constructor ───────────────────────────────────────────────────────────────

class TestMediumScraperInit:
    def test_raises_without_storage(self, mock_config, tmp_path):
        with pytest.raises(ValueError, match="StorageBackend"):
            MediumScraper(scrape_type="bulk", config=mock_config, storage=None, log_dir=str(tmp_path))

    def test_stats_initialized(self, scraper):
        assert scraper.stats["success"] == 0
        assert scraper.stats["paywalled"] == 0
        assert scraper.stats["total"] == 0
        assert scraper.stats["errors"]["parse_error"] == 0

    def test_log_dir_created(self, tmp_path, mock_config, storage):
        log_dir = tmp_path / "new_logs"
        MediumScraper(scrape_type="bulk", config=mock_config, storage=storage, log_dir=str(log_dir))
        assert log_dir.exists()


# ── filter_2025_sitemaps ──────────────────────────────────────────────────────

class TestFilter2025Sitemaps:
    SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap>
        <loc>https://medium.com/sitemap/interview-experiences-2024.xml</loc>
        <lastmod>2024-03-01</lastmod>
      </sitemap>
      <sitemap>
        <loc>https://medium.com/sitemap/python-tips-2024.xml</loc>
        <lastmod>2024-03-01</lastmod>
      </sitemap>
      <sitemap>
        <loc>https://medium.com/sitemap/interview-experiences-2022.xml</loc>
        <lastmod>2022-01-01</lastmod>
      </sitemap>
    </sitemapindex>"""

    def test_filters_by_pattern(self, scraper):
        result = scraper.filter_2025_sitemaps(self.SITEMAP_INDEX_XML)
        assert all("interview" in s.url for s in result)
        assert not any("python-tips" in s.url for s in result)

    def test_bulk_filters_by_start_date(self, scraper):
        result = scraper.filter_2025_sitemaps(self.SITEMAP_INDEX_XML)
        # 2022-01-01 is before BULK_START_DATE of 2023-01-01
        assert not any("2022" in s.url for s in result)

    def test_incremental_does_not_filter_by_date(self, scraper):
        scraper.scrape_type = "incremental"
        result = scraper.filter_2025_sitemaps(self.SITEMAP_INDEX_XML)
        # All 'interview' sitemaps pass regardless of date
        assert len(result) == 2

    def test_none_lastmod_included_in_bulk(self, scraper):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap>
            <loc>https://medium.com/sitemap/interview-no-date.xml</loc>
          </sitemap>
        </sitemapindex>"""
        result = scraper.filter_2025_sitemaps(xml)
        assert len(result) == 1


# ── extract_article_urls ──────────────────────────────────────────────────────

class TestExtractArticleUrls:
    URLSET_XML = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://medium.com/article1</loc></url>
      <url><loc>https://medium.com/article2</loc></url>
      <url><loc>https://medium.com/article3</loc></url>
    </urlset>"""

    def test_extracts_all_urls(self, scraper):
        urls = scraper.extract_article_urls(self.URLSET_XML)
        assert len(urls) == 3

    def test_urls_are_strings(self, scraper):
        urls = scraper.extract_article_urls(self.URLSET_XML)
        assert all(isinstance(u, str) for u in urls)

    def test_returns_empty_for_empty_urlset(self, scraper):
        xml = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>"""
        assert scraper.extract_article_urls(xml) == []


# ── filter_interview_urls ─────────────────────────────────────────────────────

class TestFilterInterviewUrls:
    def test_keeps_interview_urls(self, scraper):
        urls = [
            "https://medium.com/@user/my-google-interview-experience-abc123",
            "https://medium.com/@user/python-tips-xyz",
            "https://medium.com/@user/amazon-interview-prep-def456",
        ]
        result = scraper.filter_interview_urls(urls)
        assert len(result) == 2
        assert all("interview" in u for u in result)

    def test_case_insensitive(self, scraper):
        urls = ["https://medium.com/@user/My-INTERVIEW-Experience"]
        result = scraper.filter_interview_urls(urls)
        assert len(result) == 1

    def test_returns_empty_when_no_match(self, scraper):
        urls = ["https://medium.com/@user/python-tricks", "https://medium.com/@user/design-patterns"]
        assert scraper.filter_interview_urls(urls) == []

    def test_returns_empty_for_empty_input(self, scraper):
        assert scraper.filter_interview_urls([]) == []


# ── is_paywalled ──────────────────────────────────────────────────────────────

class TestIsPaywalled:
    def _soup(self, html):
        return BeautifulSoup(html, "html.parser")

    def test_detects_metered_content_class(self, scraper):
        html = '<article class="meteredContent--abc">content</article>'
        paywalled, reason = scraper.is_paywalled(self._soup(html))
        assert paywalled is True
        assert "meteredContent" in reason

    def test_detects_member_only_badge(self, scraper):
        html = "<div>Member-only story</div>"
        paywalled, reason = scraper.is_paywalled(self._soup(html))
        assert paywalled is True

    def test_detects_json_ld_not_accessible(self, scraper):
        data = json.dumps({"isAccessibleForFree": False})
        html = f'<script type="application/ld+json">{data}</script>'
        paywalled, reason = scraper.is_paywalled(self._soup(html))
        assert paywalled is True

    def test_json_ld_accessible_not_paywalled(self, scraper):
        data = json.dumps({"isAccessibleForFree": True})
        html = f'<script type="application/ld+json">{data}</script><article><p>Free content here.</p></article>'
        paywalled, _ = scraper.is_paywalled(self._soup(html))
        assert paywalled is False

    def test_detects_apollo_islocked(self, scraper):
        apollo = {"Post:abc123": {"isLocked": True}}
        html = f'<script>window.__APOLLO_STATE__ = {json.dumps(apollo)};</script>'
        paywalled, reason = scraper.is_paywalled(self._soup(html))
        assert paywalled is True
        assert "isLocked" in reason

    def test_detects_apollo_islockedpreviewonly(self, scraper):
        apollo = {"Post:abc123": {"isLockedPreviewOnly": True}}
        html = f'<script>window.__APOLLO_STATE__ = {json.dumps(apollo)};</script>'
        paywalled, reason = scraper.is_paywalled(self._soup(html))
        assert paywalled is True

    def test_detects_upgrade_cta(self, scraper):
        html = "<div>Upgrade to continue reading this article.</div>"
        paywalled, reason = scraper.is_paywalled(self._soup(html))
        assert paywalled is True

    def test_detects_subscribe_cta(self, scraper):
        html = "<div>Subscribe to read this story in full.</div>"
        paywalled, reason = scraper.is_paywalled(self._soup(html))
        assert paywalled is True

    def test_free_article_not_paywalled(self, scraper):
        html = "<article><h1>My Interview Experience</h1><p>Here is my story.</p></article>"
        paywalled, reason = scraper.is_paywalled(self._soup(html))
        assert paywalled is False
        assert reason is None


# ── extract_metadata ──────────────────────────────────────────────────────────

class TestExtractMetadata:
    def _soup(self, html):
        return BeautifulSoup(html, "html.parser")

    def test_extracts_og_description(self, scraper):
        html = '<meta property="og:description" content="A great interview story.">'
        meta = scraper.extract_metadata(self._soup(html), "https://medium.com/test")
        assert meta["description"] == "A great interview story."

    def test_extracts_reading_time(self, scraper):
        html = '<meta name="twitter:data1" content="5 min read">'
        meta = scraper.extract_metadata(self._soup(html), "https://medium.com/test")
        assert meta["reading_time"] == "5 min read"

    def test_extracts_featured_image(self, scraper):
        html = '<meta property="og:image" content="https://cdn.medium.com/image.jpg">'
        meta = scraper.extract_metadata(self._soup(html), "https://medium.com/test")
        assert meta["featured_image"] == "https://cdn.medium.com/image.jpg"

    def test_extracts_canonical_url(self, scraper):
        html = '<link rel="canonical" href="https://medium.com/@user/article-abc123">'
        meta = scraper.extract_metadata(self._soup(html), "https://medium.com/test")
        assert meta["canonical_url"] == "https://medium.com/@user/article-abc123"

    def test_extracts_tags_from_apollo_state(self, scraper):
        apollo = {"Tag:interview": {"displayTitle": "Interview", "id": "interview"}}
        html = f'<script>window.__APOLLO_STATE__ = {json.dumps(apollo)};</script>'
        meta = scraper.extract_metadata(self._soup(html), "https://medium.com/test")
        assert "Interview" in meta.get("tags", [])

    def test_returns_empty_dict_for_minimal_html(self, scraper):
        html = "<html><body><p>Just text.</p></body></html>"
        meta = scraper.extract_metadata(self._soup(html), "https://medium.com/test")
        assert isinstance(meta, dict)


# ── extract_from_apollo_state ─────────────────────────────────────────────────

class TestExtractFromApolloState:
    def _soup(self, html):
        return BeautifulSoup(html, "html.parser")

    def _make_apollo_html(self, paragraphs: dict) -> str:
        return f'<script>window.__APOLLO_STATE__ = {json.dumps(paragraphs)};</script>'

    def test_extracts_paragraphs_in_order(self, scraper):
        apollo = {
            "Paragraph:abc_1": {"text": "First paragraph.", "type": "P"},
            "Paragraph:abc_0": {"text": "Intro line.", "type": "P"},
        }
        html = self._make_apollo_html(apollo)
        content = scraper.extract_from_apollo_state(self._soup(html))
        assert content is not None
        # Index 0 should come before index 1
        assert content.index("Intro line.") < content.index("First paragraph.")

    def test_formats_headings_correctly(self, scraper):
        apollo = {
            "Paragraph:abc_0": {"text": "Section Title", "type": "H2"},
        }
        content = scraper.extract_from_apollo_state(self._soup(self._make_apollo_html(apollo)))
        assert content.startswith("## Section Title")

    def test_formats_blockquote(self, scraper):
        apollo = {"Paragraph:abc_0": {"text": "A wise quote.", "type": "PQ"}}
        content = scraper.extract_from_apollo_state(self._soup(self._make_apollo_html(apollo)))
        assert content.startswith("> A wise quote.")

    def test_formats_code_block(self, scraper):
        apollo = {"Paragraph:abc_0": {"text": "def foo(): pass", "type": "PRE"}}
        content = scraper.extract_from_apollo_state(self._soup(self._make_apollo_html(apollo)))
        assert "```" in content

    def test_formats_list_items(self, scraper):
        apollo = {"Paragraph:abc_0": {"text": "List item", "type": "ULI"}}
        content = scraper.extract_from_apollo_state(self._soup(self._make_apollo_html(apollo)))
        assert content.startswith("- List item")

    def test_returns_none_when_no_apollo_script(self, scraper):
        html = "<html><body><p>No Apollo state here.</p></body></html>"
        assert scraper.extract_from_apollo_state(self._soup(html)) is None

    def test_returns_none_when_no_paragraphs(self, scraper):
        apollo = {"SomeOtherKey:abc": {"foo": "bar"}}
        html = self._make_apollo_html(apollo)
        assert scraper.extract_from_apollo_state(self._soup(html)) is None

    def test_skips_empty_text_paragraphs(self, scraper):
        apollo = {
            "Paragraph:abc_0": {"text": "", "type": "P"},
            "Paragraph:abc_1": {"text": "   ", "type": "P"},
        }
        html = self._make_apollo_html(apollo)
        assert scraper.extract_from_apollo_state(self._soup(html)) is None


# ── parse_article ─────────────────────────────────────────────────────────────

class TestParseArticle:
    def _make_html(self, title="My Interview", content_text="", paywall=False, published="2024-01-01"):
        paywall_html = '<div>Member-only story</div>' if paywall else ''
        article_html = f'<article>{content_text}</article>' if content_text else ''
        return f"""<html><head>
          <meta property="og:title" content="{title}">
          <meta property="article:published_time" content="{published}">
        </head><body>
          {paywall_html}
          {article_html}
        </body></html>"""

    def test_returns_none_for_paywalled_article(self, scraper):
        html = self._make_html(paywall=True)
        doc, error = scraper.parse_article(html, "https://medium.com/test")
        assert doc is None
        assert "PAYWALLED" in error

    def test_extracts_title_from_og_meta(self, scraper):
        long_text = "A" * 200
        html = self._make_html(title="Google Interview 2024", content_text=f"<p>{long_text}</p>")
        doc, error = scraper.parse_article(html, "https://medium.com/test")
        assert doc is not None
        assert doc.title == "Google Interview 2024"

    def test_extracts_published_at(self, scraper):
        long_text = "B" * 200
        html = self._make_html(content_text=f"<p>{long_text}</p>", published="2024-06-01T00:00:00Z")
        doc, error = scraper.parse_article(html, "https://medium.com/test")
        assert doc is not None
        assert doc.published_at == "2024-06-01T00:00:00Z"

    def test_returns_none_for_content_too_short(self, scraper):
        html = self._make_html(content_text="<p>Short.</p>")
        doc, error = scraper.parse_article(html, "https://medium.com/test")
        assert doc is None
        assert error in ("CONTENT_TOO_SHORT", "NO_CONTENT")

    def test_returns_none_when_no_content_found(self, scraper):
        html = "<html><body><p>x</p></body></html>"
        doc, error = scraper.parse_article(html, "https://medium.com/test")
        assert doc is None

    def test_correct_source_platform(self, scraper):
        long_text = "C" * 200
        html = self._make_html(content_text=f"<p>{long_text}</p>")
        doc, error = scraper.parse_article(html, "https://medium.com/test")
        assert doc is not None
        assert doc.source_platform == "medium"

    def test_uses_apollo_state_when_available(self, scraper):
        apollo = {
            "Paragraph:x_0": {"text": "This is a paragraph from Apollo state with enough content.", "type": "P"},
            "Paragraph:x_1": {"text": "Another paragraph with enough content to pass the minimum.", "type": "P"},
            "Paragraph:x_2": {"text": "Third paragraph to ensure we meet the length threshold here.", "type": "P"},
        }
        html = f"""<html><head>
          <meta property="og:title" content="Apollo Test">
        </head><body>
          <script>window.__APOLLO_STATE__ = {json.dumps(apollo)};</script>
        </body></html>"""
        scraper.extract_from_apollo_state = MagicMock(
            return_value="Long apollo content " * 20
        )
        doc, error = scraper.parse_article(html, "https://medium.com/apollo-test")
        assert doc is not None
        scraper.extract_from_apollo_state.assert_called_once()


# ── scrape_article ────────────────────────────────────────────────────────────

class TestScrapeArticle:
    URL = "https://medium.com/@user/google-interview-experience"

    def test_returns_already_scraped_status(self, scraper, storage):
        storage.file_exists.return_value = True
        result = scraper.scrape_article(self.URL)
        assert result["status"] == "ALREADY_SCRAPED"

    def test_returns_fetch_error_status(self, scraper, storage):
        storage.file_exists.return_value = False
        scraper.fetch_html = MagicMock(return_value=(None, "HTTP_404_NOT_FOUND"))
        result = scraper.scrape_article(self.URL)
        assert result["status"] == "FETCH_ERROR"
        assert result["error_type"] == "HTTP_404_NOT_FOUND"

    def test_returns_parse_error_on_paywalled(self, scraper, storage):
        storage.file_exists.return_value = False
        scraper.fetch_html = MagicMock(return_value=("<html/>", None))
        scraper.parse_article = MagicMock(return_value=(None, "PAYWALLED (Member-only)"))
        result = scraper.scrape_article(self.URL)
        assert result["status"] == "PARSE_ERROR"
        assert "PAYWALLED" in result["error_type"]

    def test_returns_success_and_saves_document(self, scraper, storage):
        storage.file_exists.return_value = False
        mock_doc = MagicMock()
        mock_doc.document_id = "doc_abc123"
        scraper.fetch_html = MagicMock(return_value=("<html/>", None))
        scraper.parse_article = MagicMock(return_value=(mock_doc, None))
        result = scraper.scrape_article(self.URL)
        assert result["status"] == "SUCCESS"
        assert result["document_id"] == "doc_abc123"
        storage.write_json.assert_called_once()


# ── _update_stats ─────────────────────────────────────────────────────────────

class TestUpdateStats:
    def test_already_scraped_does_not_change_stats(self, scraper):
        initial = dict(scraper.stats)
        scraper._update_stats({"status": "ALREADY_SCRAPED"})
        assert scraper.stats["success"] == initial["success"]

    def test_success_increments_success(self, scraper):
        scraper._update_stats({"status": "SUCCESS"})
        assert scraper.stats["success"] == 1

    def test_paywalled_increments_paywalled(self, scraper):
        scraper._update_stats({"status": "PARSE_ERROR", "error_type": "PAYWALLED (reason)"})
        assert scraper.stats["paywalled"] == 1
        assert scraper.stats["errors"]["parse_error"] == 0

    def test_parse_error_increments_parse_error(self, scraper):
        scraper._update_stats({"status": "PARSE_ERROR", "error_type": "NO_CONTENT"})
        assert scraper.stats["errors"]["parse_error"] == 1

    def test_fetch_error_routes_to_correct_category(self, scraper):
        scraper._update_stats({"status": "FETCH_ERROR", "error_type": "HTTP_410_GONE"})
        assert scraper.stats["errors"]["http_410_gone"] == 1

    def test_unknown_status_increments_other(self, scraper):
        scraper._update_stats({"status": "UNKNOWN_STATUS"})
        assert scraper.stats["errors"]["other"] == 1

    @pytest.mark.parametrize("error_type,category", [
        ("HTTP_404_NOT_FOUND",    "http_404_not_found"),
        ("HTTP_403_FORBIDDEN",    "http_403_forbidden"),
        ("HTTP_429_RATE_LIMITED", "http_429_rate_limited"),
        ("TIMEOUT",               "timeout"),
        ("CONNECTION_ERROR",      "connection_error"),
        ("HTTP_500_SERVER_ERROR", "http_5xx_server_error"),
    ])
    def test_fetch_error_categories(self, scraper, error_type, category):
        scraper._update_stats({"status": "FETCH_ERROR", "error_type": error_type})
        assert scraper.stats["errors"][category] == 1


# ── _create_manifest ──────────────────────────────────────────────────────────

class TestMediumCreateManifest:
    def test_saves_manifest_to_storage(self, scraper):
        with patch("src.scrapers.medium.Manifest") as MockManifest:
            mock_inst = MagicMock()
            MockManifest.return_value = mock_inst
            scraper._create_manifest("2024-01-01T00:00:00Z")
            mock_inst.save.assert_called_once()

    def test_manifest_includes_correct_stats(self, scraper):
        scraper.stats["success"] = 5
        scraper.stats["paywalled"] = 3
        with patch("src.scrapers.medium.Manifest") as MockManifest:
            mock_inst = MagicMock()
            MockManifest.return_value = mock_inst
            scraper._create_manifest("2024-01-01T00:00:00Z")
            sources = MockManifest.call_args[1]["sources"]
            assert sources["medium"]["files_collected"] == 5
            assert sources["medium"]["paywalled_skipped"] == 3

    def test_total_files_matches_success_count(self, scraper):
        scraper.stats["success"] = 8
        with patch("src.scrapers.medium.Manifest") as MockManifest:
            mock_inst = MagicMock()
            MockManifest.return_value = mock_inst
            scraper._create_manifest("2024-01-01T00:00:00Z")
            assert MockManifest.call_args[1]["total_files"] == 8