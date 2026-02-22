"""
Pytest suite for the GFG scraper.
Run with: pytest tests/scrapers/test_gfg.py -v
"""

import pytest
import xml.etree.ElementTree as ET
from datetime import date
from unittest.mock import MagicMock, patch, call
import requests

from src.scrapers.gfg import GFGScraper, SitemapInfo
from src.scrapers.configs.gfg import GFGScraperConfigs


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=GFGScraperConfigs)
    cfg.SCRAPE_TYPE = "bulk"
    cfg.DELAY_SECONDS = 0
    cfg.BULK_START_DATE = "2023-01-01"
    cfg.SITEMAP_INDEX_URL = "https://www.geeksforgeeks.org/sitemap_index.xml"
    cfg.POST_SITEMAP_PREFIX = "https://www.geeksforgeeks.org/post-sitemap"
    cfg.INTERVIEW_URL_PATTERN = r".*interview-experience.*"
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
def scraper(mock_config, storage):
    return GFGScraper(scrape_type="bulk", config=mock_config, storage=storage)


# ── SitemapInfo ───────────────────────────────────────────────────────────────

class TestSitemapInfo:
    def test_lastmod_date_with_datetime_string(self):
        si = SitemapInfo(url="https://example.com", lastmod="2024-06-15T00:00:00+00:00")
        assert si.lastmod_date() == date(2024, 6, 15)

    def test_lastmod_date_with_date_only_string(self):
        si = SitemapInfo(url="https://example.com", lastmod="2024-06-15")
        assert si.lastmod_date() == date(2024, 6, 15)

    def test_lastmod_date_none_when_no_lastmod(self):
        si = SitemapInfo(url="https://example.com", lastmod=None)
        assert si.lastmod_date() is None

    def test_lastmod_date_none_on_invalid_format(self):
        si = SitemapInfo(url="https://example.com", lastmod="not-a-date")
        assert si.lastmod_date() is None

    def test_lastmod_date_empty_string(self):
        si = SitemapInfo(url="https://example.com", lastmod="")
        assert si.lastmod_date() is None


# ── Constructor ───────────────────────────────────────────────────────────────

class TestGFGScraperInit:
    def test_raises_without_storage(self, mock_config):
        with pytest.raises(ValueError, match="StorageBackend"):
            GFGScraper(scrape_type="bulk", config=mock_config, storage=None)

    def test_uses_config_scrape_type_when_not_provided(self, mock_config, storage):
        mock_config.SCRAPE_TYPE = "incremental"
        s = GFGScraper(config=mock_config, storage=storage)
        assert s.scrape_type == "incremental"

    def test_explicit_scrape_type_overrides_config(self, mock_config, storage):
        mock_config.SCRAPE_TYPE = "incremental"
        s = GFGScraper(scrape_type="bulk", config=mock_config, storage=storage)
        assert s.scrape_type == "bulk"

    def test_stats_initialized_to_zero(self, scraper):
        assert scraper.stats["files_collected"] == 0
        assert scraper.stats["errors"] == 0
        assert scraper.stats["error_urls"] == []


# ── _fetch ────────────────────────────────────────────────────────────────────

class TestFetch:
    def test_returns_text_on_success(self, scraper):
        mock_resp = MagicMock()
        mock_resp.text = "<html>ok</html>"
        scraper.session.get = MagicMock(return_value=mock_resp)
        result = scraper._fetch("https://example.com", delay=False)
        assert result == "<html>ok</html>"

    def test_returns_none_and_increments_errors_on_exception(self, scraper):
        scraper.session.get = MagicMock(side_effect=requests.RequestException("fail"))
        result = scraper._fetch("https://bad.url", delay=False)
        assert result is None
        assert scraper.stats["errors"] == 1
        assert "https://bad.url" in scraper.stats["error_urls"]

    def test_raises_for_status_on_http_error(self, scraper):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
        scraper.session.get = MagicMock(return_value=mock_resp)
        result = scraper._fetch("https://example.com/404", delay=False)
        assert result is None
        assert scraper.stats["errors"] == 1


# ── _fetch_xml ────────────────────────────────────────────────────────────────

class TestFetchXml:
    def test_returns_element_on_valid_xml(self, scraper):
        xml = '<?xml version="1.0"?><root><child/></root>'
        scraper._fetch = MagicMock(return_value=xml)
        root = scraper._fetch_xml("https://example.com/sitemap.xml")
        assert root is not None
        assert root.tag == "root"

    def test_returns_none_on_invalid_xml(self, scraper):
        scraper._fetch = MagicMock(return_value="NOT VALID XML <<<")
        assert scraper._fetch_xml("https://example.com/bad.xml") is None

    def test_returns_none_when_fetch_fails(self, scraper):
        scraper._fetch = MagicMock(return_value=None)
        assert scraper._fetch_xml("https://example.com/sitemap.xml") is None


# ── _get_sitemaps ─────────────────────────────────────────────────────────────

class TestGetSitemaps:
    SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap>
        <loc>https://www.geeksforgeeks.org/post-sitemap1.xml</loc>
        <lastmod>2024-03-01T00:00:00+00:00</lastmod>
      </sitemap>
      <sitemap>
        <loc>https://www.geeksforgeeks.org/post-sitemap2.xml</loc>
        <lastmod>2024-01-01T00:00:00+00:00</lastmod>
      </sitemap>
      <sitemap>
        <loc>https://www.geeksforgeeks.org/page-sitemap.xml</loc>
        <lastmod>2024-02-01T00:00:00+00:00</lastmod>
      </sitemap>
    </sitemapindex>"""

    def test_returns_empty_list_when_fetch_fails(self, scraper):
        scraper._fetch_xml = MagicMock(return_value=None)
        assert scraper._get_sitemaps() == []

    def test_filters_by_post_sitemap_prefix(self, scraper):
        root = ET.fromstring(self.SITEMAP_INDEX_XML)
        scraper._fetch_xml = MagicMock(return_value=root)
        sitemaps = scraper._get_sitemaps()
        urls = [s.url for s in sitemaps]
        assert all("post-sitemap" in u for u in urls)
        assert not any("page-sitemap" in u for u in urls)

    def test_sitemaps_sorted_newest_first(self, scraper):
        root = ET.fromstring(self.SITEMAP_INDEX_XML)
        scraper._fetch_xml = MagicMock(return_value=root)
        sitemaps = scraper._get_sitemaps()
        lastmods = [s.lastmod for s in sitemaps if s.lastmod]
        assert lastmods == sorted(lastmods, reverse=True)

    def test_none_lastmod_sorted_last(self, scraper):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap>
            <loc>https://www.geeksforgeeks.org/post-sitemap1.xml</loc>
          </sitemap>
          <sitemap>
            <loc>https://www.geeksforgeeks.org/post-sitemap2.xml</loc>
            <lastmod>2024-01-01</lastmod>
          </sitemap>
        </sitemapindex>"""
        root = ET.fromstring(xml)
        scraper._fetch_xml = MagicMock(return_value=root)
        sitemaps = scraper._get_sitemaps()
        # The one with a lastmod should come first
        assert sitemaps[0].lastmod is not None


# ── _filter_sitemaps ──────────────────────────────────────────────────────────

class TestFilterSitemaps:
    def _make_sitemaps(self, dates):
        return [SitemapInfo(url=f"https://example.com/sm{i}.xml", lastmod=d)
                for i, d in enumerate(dates)]

    def test_bulk_filters_by_cutoff_date(self, scraper):
        sitemaps = self._make_sitemaps(["2023-06-01", "2022-12-31", "2023-01-01"])
        result = scraper._filter_sitemaps(sitemaps)
        assert len(result) == 2
        assert all(s.lastmod >= "2023-01-01" for s in result)

    def test_bulk_includes_none_lastmod(self, scraper):
        sitemaps = self._make_sitemaps([None, "2022-01-01"])
        result = scraper._filter_sitemaps(sitemaps)
        none_sitemaps = [s for s in result if s.lastmod is None]
        assert len(none_sitemaps) == 1

    def test_incremental_with_previous_manifest(self, scraper, mock_config):
        scraper.scrape_type = "incremental"
        manifest = MagicMock()
        manifest.last_sitemap_lastmod = "2024-02-01"
        sitemaps = self._make_sitemaps(["2024-03-01", "2024-01-01", "2024-02-15"])
        with patch("src.scrapers.gfg.Manifest.get_latest", return_value=manifest):
            result = scraper._filter_sitemaps(sitemaps)
        urls_lastmod = [s.lastmod for s in result]
        assert "2024-03-01" in urls_lastmod
        assert "2024-02-15" in urls_lastmod
        assert "2024-01-01" not in urls_lastmod

    def test_incremental_no_manifest_returns_all(self, scraper):
        scraper.scrape_type = "incremental"
        sitemaps = self._make_sitemaps(["2023-01-01", "2022-06-01"])
        with patch("src.scrapers.gfg.Manifest.get_latest", return_value=None):
            result = scraper._filter_sitemaps(sitemaps)
        assert result == sitemaps


# ── _extract_interview_urls ───────────────────────────────────────────────────

class TestExtractInterviewUrls:
    SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url>
        <loc>https://www.geeksforgeeks.org/amazon-interview-experience-2024/</loc>
        <lastmod>2024-03-01</lastmod>
      </url>
      <url>
        <loc>https://www.geeksforgeeks.org/some-other-post/</loc>
        <lastmod>2024-03-01</lastmod>
      </url>
      <url>
        <loc>https://www.geeksforgeeks.org/google-interview-experience/</loc>
        <lastmod>2022-01-01</lastmod>
      </url>
    </urlset>"""

    def test_filters_non_interview_urls(self, scraper):
        sitemap = SitemapInfo(url="https://example.com/sm.xml", lastmod="2024-03-01")
        root = ET.fromstring(self.SITEMAP_XML)
        scraper._fetch_xml = MagicMock(return_value=root)
        urls = scraper._extract_interview_urls([sitemap])
        for u in urls:
            assert "interview-experience" in u["url"]

    def test_deduplicates_urls(self, scraper):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://www.geeksforgeeks.org/amazon-interview-experience/</loc></url>
          <url><loc>https://www.geeksforgeeks.org/amazon-interview-experience/</loc></url>
        </urlset>"""
        sitemaps = [SitemapInfo(url="https://example.com/sm.xml", lastmod="2024-01-01")]
        root = ET.fromstring(xml)
        scraper._fetch_xml = MagicMock(return_value=root)
        urls = scraper._extract_interview_urls(sitemaps)
        url_strings = [u["url"] for u in urls]
        assert len(url_strings) == len(set(url_strings))

    def test_bulk_filters_by_cutoff_date(self, scraper):
        sitemaps = [SitemapInfo(url="https://example.com/sm.xml", lastmod="2024-03-01")]
        root = ET.fromstring(self.SITEMAP_XML)
        scraper._fetch_xml = MagicMock(return_value=root)
        urls = scraper._extract_interview_urls(sitemaps)
        # 2022-01-01 is before BULK_START_DATE of 2023-01-01
        result_urls = [u["url"] for u in urls]
        assert not any("google-interview-experience" in u for u in result_urls)

    def test_increments_sitemaps_processed_stat(self, scraper):
        sitemaps = [SitemapInfo(url="https://example.com/sm.xml", lastmod="2024-01-01")]
        root = ET.fromstring(self.SITEMAP_XML)
        scraper._fetch_xml = MagicMock(return_value=root)
        scraper._extract_interview_urls(sitemaps)
        assert scraper.stats["sitemaps_processed"] == 1

    def test_skips_sitemap_on_fetch_failure(self, scraper):
        sitemaps = [SitemapInfo(url="https://example.com/bad.xml", lastmod="2024-01-01")]
        scraper._fetch_xml = MagicMock(return_value=None)
        urls = scraper._extract_interview_urls(sitemaps)
        assert urls == []


# ── _parse_article ────────────────────────────────────────────────────────────

class TestParseArticle:
    BASE_HTML = """<html><head></head><body>
      <h1>Amazon Interview Experience 2024</h1>
      <div class="article--viewer_content">
        <p>Round 1: DSA questions were asked.</p>
        <p>Round 2: System design.</p>
      </div>
    </body></html>"""

    def test_returns_document_with_correct_platform(self, scraper):
        doc = scraper._parse_article("https://gfg.com/test/", self.BASE_HTML)
        assert doc is not None
        assert doc.source_platform == "gfg"

    def test_extracts_h1_as_title(self, scraper):
        doc = scraper._parse_article("https://gfg.com/test/", self.BASE_HTML)
        assert doc.title == "Amazon Interview Experience 2024"

    def test_untitled_when_no_h1(self, scraper):
        html = "<html><body><p>Some content here in the body.</p></body></html>"
        doc = scraper._parse_article("https://gfg.com/test/", html)
        assert doc is not None
        assert doc.title == "Untitled"

    def test_returns_none_on_empty_content(self, scraper):
        html = "<html><body></body></html>"
        doc = scraper._parse_article("https://gfg.com/test/", html)
        assert doc is None

    def test_detects_internship_experience_type(self, scraper):
        html = """<html><body>
          <h1>Google Intern Interview Experience</h1>
          <div class="article--viewer_content"><p>I applied for an internship.</p></div>
        </body></html>"""
        doc = scraper._parse_article("https://gfg.com/test/", html)
        assert doc.source_metadata["experience_type"] == "internship"

    def test_detects_on_campus_from_tag(self, scraper):
        html = """<html><body>
          <h1>TCS Interview</h1>
          <div class="article--viewer_content"><p>On-campus drive.</p></div>
          <div class="HeadingAndChipComponent_mainContainer__dataChips">
            <a>on-campus</a>
          </div>
        </body></html>"""
        doc = scraper._parse_article("https://gfg.com/test/", html)
        assert doc.source_metadata["experience_type"] == "on-campus"

    def test_detects_off_campus_from_title(self, scraper):
        html = """<html><body>
          <h1>Off Campus Interview Experience at Microsoft</h1>
          <div class="article--viewer_content"><p>Applied through LinkedIn.</p></div>
        </body></html>"""
        doc = scraper._parse_article("https://gfg.com/test/", html)
        assert doc.source_metadata["experience_type"] == "off-campus"

    def test_unknown_experience_type_by_default(self, scraper):
        doc = scraper._parse_article("https://gfg.com/test/", self.BASE_HTML)
        assert doc.source_metadata["experience_type"] == "unknown"

    def test_extracts_published_date(self, scraper):
        html = """<html><body>
          <h1>Title</h1>
          <div class="article--viewer_content"><p>Content here.</p></div>
          <div class="ArticleHeader_last_updated_parent__XYZ">Last Updated : Jun 10, 2024</div>
        </body></html>"""
        doc = scraper._parse_article("https://gfg.com/test/", html)
        assert doc.published_at == "Jun 10, 2024"

    def test_uses_body_fallback_when_no_article_div(self, scraper):
        html = """<html><body>
          <h1>Title</h1>
          <p>Paragraph without article div wrapper.</p>
        </body></html>"""
        doc = scraper._parse_article("https://gfg.com/test/", html)
        assert doc is not None
        assert "Paragraph without article div wrapper" in doc.raw_content

    def test_source_url_preserved(self, scraper):
        url = "https://www.geeksforgeeks.org/amazon-interview-experience-2024/"
        doc = scraper._parse_article(url, self.BASE_HTML)
        assert doc.source_url == url


# ── _scrape_articles ──────────────────────────────────────────────────────────

class TestScrapeArticles:
    def test_skips_already_scraped_url(self, scraper, storage):
        storage.file_exists.return_value = True
        urls = [{"url": "https://gfg.com/amazon-interview-experience/", "lastmod": "2024-01-01"}]
        docs = scraper._scrape_articles(urls)
        assert docs == []
        assert scraper.stats["files_collected"] == 0

    def test_saves_and_counts_new_document(self, scraper, storage):
        storage.file_exists.return_value = False
        html = """<html><body>
          <h1>Google Interview Experience</h1>
          <div class="article--viewer_content"><p>Multiple rounds of interviews.</p></div>
        </body></html>"""
        scraper._fetch = MagicMock(return_value=html)
        urls = [{"url": "https://gfg.com/google-interview-experience/", "lastmod": "2024-01-01"}]
        docs = scraper._scrape_articles(urls)
        assert len(docs) == 1
        assert scraper.stats["files_collected"] == 1
        storage.write_json.assert_called_once()

    def test_increments_error_on_failed_parse(self, scraper, storage):
        storage.file_exists.return_value = False
        scraper._fetch = MagicMock(return_value="<html><body></body></html>")  # empty → parse fails
        urls = [{"url": "https://gfg.com/amazon-interview-experience/", "lastmod": "2024-01-01"}]
        scraper._scrape_articles(urls)
        assert scraper.stats["errors"] == 1

    def test_skips_url_when_fetch_returns_none(self, scraper, storage):
        storage.file_exists.return_value = False
        scraper._fetch = MagicMock(return_value=None)
        urls = [{"url": "https://gfg.com/amazon-interview-experience/", "lastmod": "2024-01-01"}]
        docs = scraper._scrape_articles(urls)
        assert docs == []


# ── _create_manifest ──────────────────────────────────────────────────────────

class TestCreateManifest:
    def test_picks_latest_lastmod(self, scraper):
        sitemaps = [
            SitemapInfo(url="https://example.com/a.xml", lastmod="2024-03-01"),
            SitemapInfo(url="https://example.com/b.xml", lastmod="2024-06-15"),
            SitemapInfo(url="https://example.com/c.xml", lastmod="2024-01-01"),
        ]
        with patch("src.scrapers.gfg.Manifest") as MockManifest:
            mock_manifest_inst = MagicMock()
            MockManifest.return_value = mock_manifest_inst
            scraper._create_manifest(sitemaps, "2024-06-15T00:00:00Z")
            call_kwargs = MockManifest.call_args[1]
            assert call_kwargs["last_sitemap_lastmod"] == "2024-06-15"

    def test_handles_no_sitemaps(self, scraper):
        with patch("src.scrapers.gfg.Manifest") as MockManifest:
            mock_manifest_inst = MagicMock()
            MockManifest.return_value = mock_manifest_inst
            scraper._create_manifest([], "2024-01-01T00:00:00Z")
            call_kwargs = MockManifest.call_args[1]
            assert call_kwargs["last_sitemap_lastmod"] is None

    def test_saves_manifest_to_storage(self, scraper):
        sitemaps = [SitemapInfo(url="https://example.com/a.xml", lastmod="2024-01-01")]
        with patch("src.scrapers.gfg.Manifest") as MockManifest:
            mock_inst = MagicMock()
            MockManifest.return_value = mock_inst
            scraper._create_manifest(sitemaps, "2024-01-01T00:00:00Z")
            mock_inst.save.assert_called_once()