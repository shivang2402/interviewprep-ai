# """
# GFG Interview Experience Scraper
# Supports bulk and incremental scraping with manifest tracking.

# Usage:
#     # Bulk scrape
#     scraper = GFGScraper(scrape_type="bulk")
#     scraper.run()

#     # Incremental scrape
#     scraper = GFGScraper(scrape_type="incremental")
#     scraper.run()
# """

# import requests
# import xml.etree.ElementTree as ET
# from bs4 import BeautifulSoup
# import json
# import time
# import os
# import re
# import hashlib
# from datetime import datetime, date, timezone
# from dataclasses import dataclass, asdict, field
# from typing import Optional, List, Dict
# from abc import ABC, abstractmethod
# from pathlib import Path


# # ============== CONFIGURATION ==============
# class ScraperConfig:
#     """Configuration for GFG Scraper"""

#     # URLs
#     SITEMAP_INDEX_URL = "https://www.geeksforgeeks.org/sitemap_index_new.xml"
#     POST_SITEMAP_PREFIX = "https://www.geeksforgeeks.org/post/"
#     INTERVIEW_URL_PATTERN = r"^https://www\.geeksforgeeks\.org/interview-experiences/[^/]*interview[^/]*"

#     # Scrape settings
#     SCRAPE_TYPE = "bulk"  # "bulk" or "incremental"
#     BULK_START_DATE = "2025-01-01"  # For bulk: only scrape lastmod >= this date
#     DELAY_SECONDS = 3
#     USER_AGENT = "InterviewPrepBot/1.0 (Academic Project; Non-commercial)"

#     # Directory structure
#     BASE_DIR = Path(__file__).resolve().parent.parent / "data"    
#     RAW_DIR = BASE_DIR / "raw" / "gfg"
#     MANIFESTS_DIR = BASE_DIR / "manifests"

#     @classmethod
#     def get_today_str(cls) -> str:
#         return date.today().isoformat()

#     @classmethod
#     def get_batch_id(cls, scrape_type: str) -> str:
#         suffix = "bulk" if scrape_type == "bulk" else "weekly"
#         return f"{cls.get_today_str()}_{suffix}"


# # ============== DATA MODELS ==============
# @dataclass
# class InterviewDocument:
#     """Unified document schema for interview experiences"""

#     # Identity & Traceability
#     document_id: str
#     source_platform: str
#     source_url: str

#     # Core Content
#     title: str
#     raw_content: str

#     # Temporal Information
#     published_at: Optional[str]  # last_update_date from GFG
#     scraped_at: str

#     # Scrape Metadata
#     scrape_type: str
#     scrape_batch_id: str

#     # Source-Specific Metadata
#     source_metadata: Dict

#     @property
#     def content_hash(self) -> str:
#         """Generate hash for deduplication (not stored)"""
#         return hashlib.md5(f"{self.title}{self.raw_content}".encode()).hexdigest()[:8]

#     @staticmethod
#     def now_iso() -> str:
#         """Get current UTC time in ISO format"""
#         return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

#     def to_dict(self) -> Dict:
#         d = asdict(self)
#         d['content_hash'] = self.content_hash
#         return d

#     @staticmethod
#     def generate_document_id(url: str) -> str:
#         """
#         Generate document_id from URL.
#         Example: https://www.geeksforgeeks.org/interview-experiences/adobe-interview.../
#         Returns: gfg_adobe_interview_experience_for_internship_on_campus
#         """
#         # Extract slug from URL
#         match = re.search(r'/interview-experiences/([^/]+)/?$', url)
#         if match:
#             slug = match.group(1)
#             # Clean and format
#             slug = re.sub(r'[^a-zA-Z0-9_-]', '_', slug)
#             slug = slug.strip('_').lower()
#             return f"gfg_{slug}"

#         # Fallback: hash the URL
#         url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
#         return f"gfg_{url_hash}"


# @dataclass
# class SitemapInfo:
#     """Sitemap metadata"""
#     url: str
#     lastmod: Optional[str]

#     def lastmod_date(self) -> Optional[date]:
#         """Parse lastmod to date object"""
#         if not self.lastmod:
#             return None
#         try:
#             # Handle various formats: 2025-01-15, 2025-01-15T10:00:00+00:00
#             date_str = self.lastmod.split('T')[0]
#             return date.fromisoformat(date_str)
#         except ValueError:
#             return None


# @dataclass
# class Manifest:
#     """Scrape manifest tracking"""
#     scrape_date: str
#     scrape_type: str
#     started_at: str
#     completed_at: Optional[str]
#     sources: Dict
#     total_files: int

#     # For incremental tracking
#     last_sitemap_lastmod: Optional[str] = None

#     def to_dict(self) -> Dict:
#         return asdict(self)

#     def save(self, filepath: Path):
#         filepath.parent.mkdir(parents=True, exist_ok=True)
#         with open(filepath, 'w') as f:
#             json.dump(self.to_dict(), f, indent=2)

#     @classmethod
#     def load(cls, filepath: Path) -> Optional['Manifest']:
#         if filepath.exists():
#             with open(filepath, 'r') as f:
#                 return cls(**json.load(f))
#         return None

#     @classmethod
#     def get_latest(cls, manifests_dir: Path) -> Optional['Manifest']:
#         """Load the most recent manifest file"""
#         if not manifests_dir.exists():
#             return None

#         manifest_files = sorted(manifests_dir.glob("scrape_*.json"), reverse=True)
#         if manifest_files:
#             return cls.load(manifest_files[0])
#         return None


# # ============== GFG SCRAPER CLASS ==============
# class GFGScraper:
#     """
#     GeeksforGeeks Interview Experience Scraper

#     Supports:
#     - Bulk scraping: All articles with lastmod >= configured date
#     - Incremental scraping: New articles since last manifest
#     """

#     def __init__(self, scrape_type: str = None, config: ScraperConfig = None):
#         self.config = config or ScraperConfig()
#         self.scrape_type = scrape_type or self.config.SCRAPE_TYPE
#         self.batch_id = self.config.get_batch_id(self.scrape_type)

#         # Setup session with browser-like headers
#         self.session = requests.Session()
#         self.session.headers.update({
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
#             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
#             'Accept-Language': 'en-US,en;q=0.5',
#             'Accept-Encoding': 'gzip, deflate, br',
#             'Connection': 'keep-alive',
#             'Upgrade-Insecure-Requests': '1'
#         })

#         # Setup directories
#         self.today_raw_dir = self.config.RAW_DIR / self.config.get_today_str()
#         self.today_raw_dir.mkdir(parents=True, exist_ok=True)
#         # self.config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
#         self.config.MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)

#         # Stats tracking
#         self.stats = {
#             "files_collected": 0,
#             "sitemaps_processed": 0,
#             "urls_found": 0,
#             "errors": 0,
#             "error_urls": []
#         }

#     # ─────────── HTTP Methods ───────────
#     def _fetch(self, url: str, delay: bool = True) -> Optional[str]:
#         """Fetch URL with rate limiting"""
#         try:
#             if delay:
#                 time.sleep(self.config.DELAY_SECONDS)

#             response = self.session.get(url, timeout=30)
#             response.raise_for_status()
#             return response.text

#         except requests.RequestException as e:
#             print(f"    ERROR fetching {url}: {e}")
#             self.stats["errors"] += 1
#             self.stats["error_urls"].append(url)
#             return None

#     def _fetch_xml(self, url: str) -> Optional[ET.Element]:
#         """Fetch and parse XML"""
#         content = self._fetch(url)
#         if content:
#             try:
#                 return ET.fromstring(content)
#             except ET.ParseError as e:
#                 print(f"    ERROR parsing XML: {e}")
#         return None

#     # ─────────── Sitemap Processing ───────────
#     def _get_sitemaps(self) -> List[SitemapInfo]:
#         """Fetch and filter sitemaps from index"""
#         print("\n[1/3] Fetching sitemap index...")

#         root = self._fetch_xml(self.config.SITEMAP_INDEX_URL)
#         if root is None:
#             return []

#         sitemaps = []
#         ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

#         # Try with namespace
#         for sitemap_elem in root.findall('.//ns:sitemap', ns):
#             loc = sitemap_elem.find('ns:loc', ns)
#             lastmod = sitemap_elem.find('ns:lastmod', ns)

#             if loc is not None and loc.text:
#                 url = loc.text.strip()
#                 if url.startswith(self.config.POST_SITEMAP_PREFIX):
#                     sitemaps.append(SitemapInfo(
#                         url=url,
#                         lastmod=lastmod.text.strip() if lastmod is not None and lastmod.text else None
#                     ))

#         # Fallback without namespace
#         if not sitemaps:
#             for sitemap_elem in root.iter():
#                 if sitemap_elem.tag.endswith('sitemap'):
#                     loc = lastmod = None
#                     for child in sitemap_elem:
#                         if child.tag.endswith('loc') and child.text:
#                             loc = child.text.strip()
#                         if child.tag.endswith('lastmod') and child.text:
#                             lastmod = child.text.strip()
#                     if loc and loc.startswith(self.config.POST_SITEMAP_PREFIX):
#                         sitemaps.append(SitemapInfo(url=loc, lastmod=lastmod))

#         # Sort by lastmod descending
#         sitemaps.sort(
#             key=lambda x: x.lastmod if x.lastmod else "0000-00-00",
#             reverse=True
#         )

#         print(f"    Found {len(sitemaps)} post sitemaps")
#         return sitemaps

#     def _filter_sitemaps(self, sitemaps: List[SitemapInfo]) -> List[SitemapInfo]:
#         """Filter sitemaps based on scrape type"""

#         if self.scrape_type == "bulk":
#             # Bulk: filter by configured start date
#             cutoff = date.fromisoformat(self.config.BULK_START_DATE)
#             filtered = []
#             for s in sitemaps:
#                 s_date = s.lastmod_date()
#                 if s_date is None or s_date >= cutoff:
#                     filtered.append(s)
#             print(f"    Filtered to {len(filtered)} sitemaps (lastmod >= {cutoff})")
#             return filtered

#         else:
#             # Incremental: filter by last manifest's lastmod
#             last_manifest = Manifest.get_latest(self.config.MANIFESTS_DIR)

#             if last_manifest and last_manifest.last_sitemap_lastmod:
#                 cutoff_str = last_manifest.last_sitemap_lastmod
#                 filtered = [s for s in sitemaps if s.lastmod and s.lastmod > cutoff_str]
#                 print(f"    Incremental: {len(filtered)} sitemaps newer than {cutoff_str}")
#                 return filtered
#             else:
#                 print("    No previous manifest found, processing all sitemaps")
#                 return sitemaps

#     def _extract_interview_urls(self, sitemaps: List[SitemapInfo]) -> List[Dict]:
#         """Extract interview URLs from sitemaps with lastmod filtering"""
#         print(f"\n[2/3] Extracting interview URLs from {len(sitemaps)} sitemaps...")

#         pattern = re.compile(self.config.INTERVIEW_URL_PATTERN)
#         all_urls = []

#         # Determine cutoff date based on scrape type
#         if self.scrape_type == "bulk":
#             cutoff_date = self.config.BULK_START_DATE
#         else:
#             # Incremental: get from last manifest
#             last_manifest = Manifest.get_latest(self.config.MANIFESTS_DIR)
#             if last_manifest and last_manifest.last_sitemap_lastmod:
#                 cutoff_date = last_manifest.last_sitemap_lastmod.split('T')[0]
#             else:
#                 cutoff_date = None

#         print(f"    URL lastmod cutoff: {cutoff_date or 'None (all URLs)'}")

#         for i, sitemap in enumerate(sitemaps):
#             print(f"    [{i+1}/{len(sitemaps)}] Processing {sitemap.url[:60]}...")

#             root = self._fetch_xml(sitemap.url)
#             if root is None:
#                 continue

#             # Extract URLs with their lastmod
#             urls_in_sitemap = []
#             ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

#             # Try with namespace first
#             for url_elem in root.findall('.//ns:url', ns):
#                 loc = url_elem.find('ns:loc', ns)
#                 lastmod = url_elem.find('ns:lastmod', ns)

#                 if loc is not None and loc.text:
#                     urls_in_sitemap.append({
#                         "url": loc.text.strip(),
#                         "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else None
#                     })

#             # Fallback without namespace
#             if not urls_in_sitemap:
#                 for url_elem in root.iter():
#                     if url_elem.tag.endswith('url'):
#                         loc = lastmod = None
#                         for child in url_elem:
#                             if child.tag.endswith('loc') and child.text:
#                                 loc = child.text.strip()
#                             if child.tag.endswith('lastmod') and child.text:
#                                 lastmod = child.text.strip()
#                         if loc:
#                             urls_in_sitemap.append({"url": loc, "lastmod": lastmod})

#             # Filter for interview experiences matching regex
#             interview_urls = [u for u in urls_in_sitemap if pattern.match(u["url"])]

#             # Filter by lastmod cutoff
#             if cutoff_date:
#                 filtered_urls = []
#                 for u in interview_urls:
#                     if u["lastmod"]:
#                         url_date = u["lastmod"].split('T')[0]
#                         if url_date >= cutoff_date:
#                             filtered_urls.append(u)
#                     # If no lastmod, include in bulk but exclude in incremental
#                     elif self.scrape_type == "bulk":
#                         filtered_urls.append(u)
#                 interview_urls = filtered_urls

#             all_urls.extend(interview_urls)
#             print(f"        Found {len(interview_urls)} interview URLs (after lastmod filter)")
#             self.stats["sitemaps_processed"] += 1

#             break

#         # Deduplicate by URL
#         seen = set()
#         unique_urls = []
#         for u in all_urls:
#             if u["url"] not in seen:
#                 seen.add(u["url"])
#                 unique_urls.append(u)

#         self.stats["urls_found"] = len(unique_urls)
#         print(f"    Total unique interview URLs: {len(unique_urls)}")

#         return unique_urls

#     # ─────────── Article Parsing ───────────
#     def _parse_article(self, url: str, html: str) -> Optional[InterviewDocument]:
#         """Parse a GFG interview experience article"""
#         soup = BeautifulSoup(html, 'html.parser')

#         # Extract title
#         title_tag = soup.find('h1')
#         title = title_tag.get_text(strip=True) if title_tag else "Untitled"

#         # Extract main content from article viewer
#         article = soup.find('div', class_=lambda c: c and 'article--viewer' in c)

#         if article:
#             # Remove unwanted sidebar content
#             for unwanted in article.find_all('div', class_=lambda c: c and 'LeftbarOutsideIndiaContent' in str(c)):
#                 unwanted.decompose()

#             for tag in article.find_all(['script', 'style', 'nav', 'footer', 'aside']):
#                 tag.decompose()

#             raw_content = article.get_text(separator='\n', strip=True)
#         else:
#             # Fallback
#             body = soup.find('body')
#             if body:
#                 for tag in body.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside']):
#                     tag.decompose()
#                 raw_content = body.get_text(separator='\n', strip=True)
#             else:
#                 raw_content = ""

#         if not raw_content:
#             return None

#         # Extract last_update_date
#         published_at = None
#         date_div = soup.find('div', class_=lambda c: c and 'ArticleHeader_last_updated_parent' in str(c))
#         if date_div:
#             date_text = date_div.get_text(strip=True)
#             match = re.search(r'Last Updated\s*:\s*(.+)', date_text)
#             if match:
#                 published_at = match.group(1).strip()

#         # Extract tags
#         tags = []
#         tags_container = soup.find('div', class_=lambda c: c and 'HeadingAndChipComponent_mainContainer__dataChips' in str(c))
#         if tags_container:
#             for tag_elem in tags_container.find_all('a'):
#                 tag_text = tag_elem.get_text(strip=True)
#                 if tag_text and tag_text not in tags:
#                     tags.append(tag_text)

#         # Determine experience type
#         exp_type = "unknown"
#         tags_lower = [t.lower() for t in tags]
#         title_lower = title.lower()
#         if "on-campus" in tags_lower or "on campus" in title_lower:
#             exp_type = "on-campus"
#         elif "off-campus" in tags_lower or "off campus" in title_lower:
#             exp_type = "off-campus"
#         elif "internship" in tags_lower or "intern" in title_lower:
#             exp_type = "internship"

#         return InterviewDocument(
#             document_id=InterviewDocument.generate_document_id(url),
#             source_platform="gfg",
#             source_url=url,
#             title=title,
#             raw_content=raw_content,
#             published_at=published_at,
#             scraped_at=InterviewDocument.now_iso(),
#             scrape_type=self.scrape_type,
#             scrape_batch_id=self.batch_id,
#             source_metadata={
#                 "tags": tags,
#                 "experience_type": exp_type
#             }
#         )

#     # ─────────── Scraping ───────────
#     def _scrape_articles(self, urls: List[Dict]) -> List[InterviewDocument]:
#         """Scrape all article URLs"""
#         print(f"\n[3/3] Scraping {len(urls)} articles...")

#         documents = []

#         for i, url_data in enumerate(urls):
#             url = url_data["url"]
#             print(f"    [{i+1}/{len(urls)}] {url[:65]}...")

#             html = self._fetch(url)
#             if html is None:
#                 continue

#             doc = self._parse_article(url, html)
#             if doc:
#                 # Save individual file
#                 self._save_document(doc)
#                 documents.append(doc)
#                 self.stats["files_collected"] += 1
#             else:
#                 print(f"        WARNING: Could not parse content")
#                 self.stats["errors"] += 1
#                 self.stats["error_urls"].append(url)

#         return documents

#     def _save_document(self, doc: InterviewDocument):
#         """Save document to individual JSON file"""
#         filename = f"{doc.document_id}.json"
#         filepath = self.today_raw_dir / filename

#         with open(filepath, 'w', encoding='utf-8') as f:
#             json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

#     # ─────────── Manifest ───────────
#     def _create_manifest(self, sitemaps: List[SitemapInfo], started_at: str) -> Manifest:
#         """Create and save manifest"""

#         # Get latest sitemap lastmod for incremental tracking
#         latest_lastmod = None
#         if sitemaps:
#             latest_lastmod = max(
#                 (s.lastmod for s in sitemaps if s.lastmod),
#                 default=None
#             )

#         manifest = Manifest(
#             scrape_date=self.config.get_today_str(),
#             scrape_type=self.scrape_type,
#             started_at=started_at,
#             completed_at=InterviewDocument.now_iso(),
#             sources={
#                 "gfg": {
#                     "files_collected": self.stats["files_collected"],
#                     "sitemaps_processed": self.stats["sitemaps_processed"],
#                     "urls_found": self.stats["urls_found"],
#                     "errors": self.stats["errors"],
#                     "error_urls": self.stats["error_urls"][:10]  # Limit stored errors
#                 }
#             },
#             total_files=self.stats["files_collected"],
#             last_sitemap_lastmod=latest_lastmod
#         )

#         manifest_path = self.config.MANIFESTS_DIR / f"scrape_{self.config.get_today_str()}.json"
#         manifest.save(manifest_path)
#         print(f"\nManifest saved to {manifest_path}")

#         return manifest

#     # ─────────── Main Entry Point ───────────
#     def run(self):
#         """Execute the scraping pipeline"""
#         print("=" * 60)
#         print(f"GFG Interview Scraper - {self.scrape_type.upper()} mode")
#         print("=" * 60)
#         print(f"Batch ID: {self.batch_id}")
#         print(f"Output directory: {self.today_raw_dir}")

#         started_at = InterviewDocument.now_iso()

#         # Step 1: Get sitemaps
#         sitemaps = self._get_sitemaps()
#         if not sitemaps:
#             print("ERROR: No sitemaps found. Exiting.")
#             return

#         # Filter sitemaps based on scrape type
#         sitemaps = self._filter_sitemaps(sitemaps)
#         if not sitemaps:
#             print("No sitemaps to process after filtering. Exiting.")
#             return

#         # Step 2: Extract interview URLs
#         urls = self._extract_interview_urls(sitemaps)
#         if not urls:
#             print("No interview URLs found. Exiting.")
#             return

#         # Step 3: Scrape articles
#         documents = self._scrape_articles(urls)

#         # Create manifest
#         manifest = self._create_manifest(sitemaps, started_at)

#         # Summary
#         print("\n" + "=" * 60)
#         print("SCRAPE COMPLETE")
#         print("=" * 60)
#         print(f"Files collected: {self.stats['files_collected']}")
#         print(f"Errors: {self.stats['errors']}")
#         print(f"Output: {self.today_raw_dir}")


# # ============== ENTRY POINT ==============
# if __name__ == "__main__":
#     # import argparse

#     # parser = argparse.ArgumentParser(description="GFG Interview Scraper")
#     # parser.add_argument(
#     #     "--type",
#     #     choices=["bulk", "incremental"],
#     #     default="bulk",
#     #     help="Scrape type: bulk or incremental"
#     # )

#     # args = parser.parse_args()

#     scraper = GFGScraper(scrape_type="bulk")
#     scraper.run()


"""
GFG Interview Experience Scraper (GCS-compatible)
Supports bulk and incremental scraping with manifest tracking.
Works with both local filesystem and Google Cloud Storage.

Usage:
    from storage_backend import GCSStorageBackend, LocalStorageBackend

    # --- Option A: Store in GCS (production) ---
    storage = GCSStorageBackend(bucket_name="interview-scraper-data")
    scraper = GFGScraper(scrape_type="bulk", storage=storage)
    scraper.run()

    # --- Option B: Store locally (development) ---
    storage = LocalStorageBackend(base_dir=Path("data"))
    scraper = GFGScraper(scrape_type="bulk", storage=storage)
    scraper.run()
"""

import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import time
import re
import hashlib
from datetime import datetime, date, timezone
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict
from pathlib import Path

from src.storage.storage_backend import StorageBackend
from src.storage.gcs_backend import GCSBackend

# ============== CONFIGURATION ==============
class ScraperConfig:
    """Configuration for GFG Scraper"""

    SITEMAP_INDEX_URL = "https://www.geeksforgeeks.org/sitemap_index_new.xml"
    POST_SITEMAP_PREFIX = "https://www.geeksforgeeks.org/post/"
    INTERVIEW_URL_PATTERN = r"^https://www\.geeksforgeeks\.org/interview-experiences/[^/]*interview[^/]*"

    SCRAPE_TYPE = "bulk"
    BULK_START_DATE = "2025-01-01"
    DELAY_SECONDS = 3
    USER_AGENT = "InterviewPrepBot/1.0 (Academic Project; Non-commercial)"

    # Relative paths within storage (no more absolute Path references)
    RAW_PREFIX = "raw/gfg"
    MANIFESTS_PREFIX = "manifests"

    @classmethod
    def get_today_str(cls) -> str:
        return date.today().isoformat()

    @classmethod
    def get_batch_id(cls, scrape_type: str) -> str:
        suffix = "bulk" if scrape_type == "bulk" else "weekly"
        return f"{cls.get_today_str()}_{suffix}"


# ============== DATA MODELS ==============
@dataclass
class InterviewDocument:
    """Unified document schema for interview experiences"""

    document_id: str
    source_platform: str
    source_url: str
    title: str
    raw_content: str
    published_at: Optional[str]
    scraped_at: str
    scrape_type: str
    scrape_batch_id: str
    source_metadata: Dict

    @property
    def content_hash(self) -> str:
        return hashlib.md5(f"{self.title}{self.raw_content}".encode()).hexdigest()

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["content_hash"] = self.content_hash
        return d

    @staticmethod
    def generate_document_id(url: str) -> str:
        match = re.search(r"/interview-experiences/([^/]+)/?$", url)
        if match:
            slug = match.group(1)
            slug = re.sub(r"[^a-zA-Z0-9_-]", "_", slug)
            slug = slug.strip("_").lower()
            return f"gfg_{slug}"
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"gfg_{url_hash}"


@dataclass
class SitemapInfo:
    url: str
    lastmod: Optional[str]

    def lastmod_date(self) -> Optional[date]:
        if not self.lastmod:
            return None
        try:
            date_str = self.lastmod.split("T")[0]
            return date.fromisoformat(date_str)
        except ValueError:
            return None


@dataclass
class Manifest:
    """Scrape manifest — now uses StorageBackend instead of direct file I/O"""

    scrape_date: str
    scrape_type: str
    started_at: str
    completed_at: Optional[str]
    sources: Dict
    total_files: int
    last_sitemap_lastmod: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    def save(self, storage: StorageBackend, path: str):
        """Save manifest via storage backend."""
        storage.write_json(path, self.to_dict())

    @classmethod
    def load(cls, storage: StorageBackend, path: str) -> Optional["Manifest"]:
        """Load manifest from storage backend."""
        data = storage.read_json(path)
        if data:
            return cls(**data)
        return None

    @classmethod
    def get_latest(cls, storage: StorageBackend, manifests_prefix: str) -> Optional["Manifest"]:
        """Load the most recent manifest file from storage."""
        # list_files returns sorted descending, so first match is latest
        files = storage.list_files(prefix=manifests_prefix, suffix=".json")
        # Filter to only scrape_ manifests
        manifest_files = [f for f in files if "scrape_" in f]
        if manifest_files:
            return cls.load(storage, manifest_files[0])
        return None


# ============== GFG SCRAPER CLASS ==============
class GFGScraper:
    """
    GeeksforGeeks Interview Experience Scraper
    Now accepts a StorageBackend for flexible output (local or GCS).
    """

    def __init__(
        self,
        scrape_type: str = None,
        config: ScraperConfig = None,
        storage: StorageBackend = None,
    ):
        self.config = config or ScraperConfig()
        self.scrape_type = scrape_type or self.config.SCRAPE_TYPE
        self.batch_id = self.config.get_batch_id(self.scrape_type)
        self.storage = storage

        # Build relative paths for this run
        self.today_raw_prefix = f"{self.config.RAW_PREFIX}/{self.config.get_today_str()}"
        self.manifests_prefix = self.config.MANIFESTS_PREFIX

        # Session setup
        # self.session = requests.Session()
        # self.session.headers.update({
        #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        #     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        #     "Accept-Language": "en-US,en;q=0.5",
        #     "Accept-Encoding": "gzip, deflate, br",
        #     "Connection": "keep-alive",
        # })

        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        self.stats = {
            "files_collected": 0,
            "sitemaps_processed": 0,
            "urls_found": 0,
            "errors": 0,
            "error_urls": [],
        }

    # ─────────── HTTP Methods ───────────
    def _fetch(self, url: str, delay: bool = True) -> Optional[str]:
        try:
            if delay:
                time.sleep(self.config.DELAY_SECONDS)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"    ERROR fetching {url}: {e}")
            self.stats["errors"] += 1
            self.stats["error_urls"].append(url)
            return None

    def _fetch_xml(self, url: str) -> Optional[ET.Element]:
        content = self._fetch(url)
        if content:
            try:
                return ET.fromstring(content)
            except ET.ParseError as e:
                print(f"    ERROR parsing XML: {e}")
        return None

    # ─────────── Sitemap Processing ───────────
    def _get_sitemaps(self) -> List[SitemapInfo]:
        print("\n[1/3] Fetching sitemap index...")
        root = self._fetch_xml(self.config.SITEMAP_INDEX_URL)
        if root is None:
            return []

        sitemaps = []
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        for sitemap_elem in root.findall(".//ns:sitemap", ns):
            loc = sitemap_elem.find("ns:loc", ns)
            lastmod = sitemap_elem.find("ns:lastmod", ns)
            if loc is not None and loc.text:
                url = loc.text.strip()
                if url.startswith(self.config.POST_SITEMAP_PREFIX):
                    sitemaps.append(SitemapInfo(
                        url=url,
                        lastmod=lastmod.text.strip() if lastmod is not None and lastmod.text else None,
                    ))

        if not sitemaps:
            for sitemap_elem in root.iter():
                if sitemap_elem.tag.endswith("sitemap"):
                    loc = lastmod = None
                    for child in sitemap_elem:
                        if child.tag.endswith("loc") and child.text:
                            loc = child.text.strip()
                        if child.tag.endswith("lastmod") and child.text:
                            lastmod = child.text.strip()
                    if loc and loc.startswith(self.config.POST_SITEMAP_PREFIX):
                        sitemaps.append(SitemapInfo(url=loc, lastmod=lastmod))

        sitemaps.sort(key=lambda x: x.lastmod if x.lastmod else "0000-00-00", reverse=True)
        print(f"    Found {len(sitemaps)} post sitemaps")
        return sitemaps

    def _filter_sitemaps(self, sitemaps: List[SitemapInfo]) -> List[SitemapInfo]:
        if self.scrape_type == "bulk":
            cutoff = date.fromisoformat(self.config.BULK_START_DATE)
            filtered = [s for s in sitemaps if s.lastmod_date() is None or s.lastmod_date() >= cutoff]
            print(f"    Filtered to {len(filtered)} sitemaps (lastmod >= {cutoff})")
            return filtered
        else:
            last_manifest = Manifest.get_latest(self.storage, self.manifests_prefix)
            if last_manifest and last_manifest.last_sitemap_lastmod:
                cutoff_str = last_manifest.last_sitemap_lastmod
                filtered = [s for s in sitemaps if s.lastmod and s.lastmod > cutoff_str]
                print(f"    Incremental: {len(filtered)} sitemaps newer than {cutoff_str}")
                return filtered
            else:
                print("    No previous manifest found, processing all sitemaps")
                return sitemaps

    def _extract_interview_urls(self, sitemaps: List[SitemapInfo]) -> List[Dict]:
        print(f"\n[2/3] Extracting interview URLs from {len(sitemaps)} sitemaps...")
        pattern = re.compile(self.config.INTERVIEW_URL_PATTERN)
        all_urls = []

        if self.scrape_type == "bulk":
            cutoff_date = self.config.BULK_START_DATE
        else:
            last_manifest = Manifest.get_latest(self.storage, self.manifests_prefix)
            if last_manifest and last_manifest.last_sitemap_lastmod:
                cutoff_date = last_manifest.last_sitemap_lastmod.split("T")[0]
            else:
                cutoff_date = None

        print(f"    URL lastmod cutoff: {cutoff_date or 'None (all URLs)'}")

        for i, sitemap in enumerate(sitemaps):
            print(f"    [{i+1}/{len(sitemaps)}] Processing {sitemap.url[:60]}...")
            root = self._fetch_xml(sitemap.url)
            if root is None:
                continue

            urls_in_sitemap = []
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            for url_elem in root.findall(".//ns:url", ns):
                loc = url_elem.find("ns:loc", ns)
                lastmod = url_elem.find("ns:lastmod", ns)
                if loc is not None and loc.text:
                    urls_in_sitemap.append({
                        "url": loc.text.strip(),
                        "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else None,
                    })

            if not urls_in_sitemap:
                for url_elem in root.iter():
                    if url_elem.tag.endswith("url"):
                        loc = lastmod = None
                        for child in url_elem:
                            if child.tag.endswith("loc") and child.text:
                                loc = child.text.strip()
                            if child.tag.endswith("lastmod") and child.text:
                                lastmod = child.text.strip()
                        if loc:
                            urls_in_sitemap.append({"url": loc, "lastmod": lastmod})

            interview_urls = [u for u in urls_in_sitemap if pattern.match(u["url"])]

            if cutoff_date:
                filtered_urls = []
                for u in interview_urls:
                    if u["lastmod"]:
                        if u["lastmod"].split("T")[0] >= cutoff_date:
                            filtered_urls.append(u)
                    elif self.scrape_type == "bulk":
                        filtered_urls.append(u)
                interview_urls = filtered_urls

            all_urls.extend(interview_urls)
            print(f"        Found {len(interview_urls)} interview URLs (after lastmod filter)")
            self.stats["sitemaps_processed"] += 1
            break  # Keeping your original break

        seen = set()
        unique_urls = []
        for u in all_urls:
            if u["url"] not in seen:
                seen.add(u["url"])
                unique_urls.append(u)

        self.stats["urls_found"] = len(unique_urls)
        print(f"    Total unique interview URLs: {len(unique_urls)}")
        return unique_urls

    # ─────────── Article Parsing ───────────
    def _parse_article(self, url: str, html: str) -> Optional[InterviewDocument]:
        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else "Untitled"

        article = soup.find("div", class_=lambda c: c and "article--viewer" in c)

        if article:
            for unwanted in article.find_all("div", class_=lambda c: c and "LeftbarOutsideIndiaContent" in str(c)):
                unwanted.decompose()
            for tag in article.find_all(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()
            raw_content = article.get_text(separator="\n", strip=True)
        else:
            body = soup.find("body")
            if body:
                for tag in body.find_all(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                raw_content = body.get_text(separator="\n", strip=True)
            else:
                raw_content = ""

        if not raw_content:
            return None

        published_at = None
        date_div = soup.find("div", class_=lambda c: c and "ArticleHeader_last_updated_parent" in str(c))
        if date_div:
            date_text = date_div.get_text(strip=True)
            match = re.search(r"Last Updated\s*:\s*(.+)", date_text)
            if match:
                published_at = match.group(1).strip()

        tags = []
        tags_container = soup.find("div", class_=lambda c: c and "HeadingAndChipComponent_mainContainer__dataChips" in str(c))
        if tags_container:
            for tag_elem in tags_container.find_all("a"):
                tag_text = tag_elem.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)

        exp_type = "unknown"
        tags_lower = [t.lower() for t in tags]
        title_lower = title.lower()
        if "on-campus" in tags_lower or "on campus" in title_lower:
            exp_type = "on-campus"
        elif "off-campus" in tags_lower or "off campus" in title_lower:
            exp_type = "off-campus"
        elif "internship" in tags_lower or "intern" in title_lower:
            exp_type = "internship"

        return InterviewDocument(
            document_id=InterviewDocument.generate_document_id(url),
            source_platform="gfg",
            source_url=url,
            title=title,
            raw_content=raw_content,
            published_at=published_at,
            scraped_at=InterviewDocument.now_iso(),
            scrape_type=self.scrape_type,
            scrape_batch_id=self.batch_id,
            source_metadata={"tags": tags, "experience_type": exp_type},
        )

    # ─────────── Scraping ───────────
    def _scrape_articles(self, urls: List[Dict]) -> List[InterviewDocument]:
        print(f"\n[3/3] Scraping {len(urls)} articles...")
        documents = []

        for i, url_data in enumerate(urls):
            url = url_data["url"]
            print(f"    [{i+1}/{len(urls)}] {url[:65]}...")

            html = self._fetch(url)
            if html is None:
                continue

            doc = self._parse_article(url, html)
            if doc:
                self._save_document(doc)
                documents.append(doc)
                self.stats["files_collected"] += 1
            else:
                print(f"        WARNING: Could not parse content")
                self.stats["errors"] += 1
                self.stats["error_urls"].append(url)

        return documents

    def _save_document(self, doc: InterviewDocument):
        """Save document via storage backend — works for both local and GCS."""
        path = f"{self.today_raw_prefix}/{doc.document_id}.json"
        self.storage.write_json(path, doc.to_dict())

    # ─────────── Manifest ───────────
    def _create_manifest(self, sitemaps: List[SitemapInfo], started_at: str) -> Manifest:
        latest_lastmod = None
        if sitemaps:
            latest_lastmod = max(
                (s.lastmod for s in sitemaps if s.lastmod), default=None
            )

        manifest = Manifest(
            scrape_date=self.config.get_today_str(),
            scrape_type=self.scrape_type,
            started_at=started_at,
            completed_at=InterviewDocument.now_iso(),
            sources={
                "gfg": {
                    "files_collected": self.stats["files_collected"],
                    "sitemaps_processed": self.stats["sitemaps_processed"],
                    "urls_found": self.stats["urls_found"],
                    "errors": self.stats["errors"],
                    "error_urls": self.stats["error_urls"][:10],
                }
            },
            total_files=self.stats["files_collected"],
            last_sitemap_lastmod=latest_lastmod,
        )

        manifest_path = f"{self.manifests_prefix}/scrape_{self.config.get_today_str()}.json"
        manifest.save(self.storage, manifest_path)
        print(f"\nManifest saved to {manifest_path}")
        return manifest

    # ─────────── Main Entry Point ───────────
    def run(self):
        print("=" * 60)
        print(f"GFG Interview Scraper - {self.scrape_type.upper()} mode")
        print(f"Storage: {self.storage.__class__.__name__}")
        print("=" * 60)
        print(f"Batch ID: {self.batch_id}")

        started_at = InterviewDocument.now_iso()

        sitemaps = self._get_sitemaps()
        if not sitemaps:
            print("ERROR: No sitemaps found. Exiting.")
            return

        sitemaps = self._filter_sitemaps(sitemaps)
        if not sitemaps:
            print("No sitemaps to process after filtering. Exiting.")
            return

        urls = self._extract_interview_urls(sitemaps)
        if not urls:
            print("No interview URLs found. Exiting.")
            return

        documents = self._scrape_articles(urls)
        manifest = self._create_manifest(sitemaps, started_at)

        print("\n" + "=" * 60)
        print("SCRAPE COMPLETE")
        print("=" * 60)
        print(f"Files collected: {self.stats['files_collected']}")
        print(f"Errors: {self.stats['errors']}")


# ============== ENTRY POINT ==============
if __name__ == "__main__":
    # ── Choose your storage backend ──

    # Option 1: GCS (production)
    storage = GCSBackend(bucket_name="interviewprep-ai-data", credentials_path=rf"C:\Users\heetk\Downloads\interviewprep-ai\connection_string.json")

    # Option 2: Local (development)
    # storage = LocalStorageBackend(base_dir=Path("data"))

    scraper = GFGScraper(scrape_type="bulk", storage=storage)
    scraper.run()