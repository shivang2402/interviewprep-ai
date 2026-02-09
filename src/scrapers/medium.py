"""Medium article scraper."""

from playwright.sync_api import sync_playwright
import xml.etree.ElementTree as ET
import os
import time
import json
import re
import logging
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from datetime import datetime, timezone
from pathlib import Path

try:
    from .utils import (
        generate_document_id,
        generate_content_hash,
        random_delay,
        categorize_error
    )
except ImportError:
    from utils import (
        generate_document_id,
        generate_content_hash,
        random_delay,
        categorize_error
    )

class MediumScraper:
    """Object-oriented Medium article scraper."""
    
    def __init__(self, output_dir, log_file=None):
        """
        Initialize the Medium scraper.
        
        Args:
            output_dir: Directory to save scraped articles
            log_file: Optional path to log file (defaults to output_dir/medium_scraper_log.txt)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_file = log_file or self.output_dir / "medium_scraper_log.txt"
        self.logger = self._setup_logging()
        
        self.stats = {
            "total": 0,
            "success": 0,
            "paywalled": 0,
            "errors": {
                "http_410_gone": 0,
                "http_404_not_found": 0,
                "http_403_forbidden": 0,
                "http_429_rate_limited": 0,
                "http_5xx_server_error": 0,
                "timeout": 0,
                "connection_error": 0,
                "parse_error": 0,
                "other": 0
            }
        }
    
    def _setup_logging(self):
        """Setup logging configuration."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(self.log_file, mode='w', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        
        # Reduce console verbosity
        console_handler = logging.getLogger().handlers[1]
        console_handler.setLevel(logging.WARNING)
        
        return logging.getLogger(__name__)
    
    # ========================================================================
    # SITEMAP METHODS
    # ========================================================================
    
    def fetch_sitemap(self, url):
        """Fetch sitemap using Playwright."""
        download_path = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    accept_downloads=True
                )
                page = context.new_page()
                
                download = None
                try:
                    with page.expect_download(timeout=15000) as download_info:
                        try:
                            page.goto(url, timeout=30000)
                        except Exception as e:
                            if "Download is starting" not in str(e):
                                raise
                    download = download_info.value
                except Exception:
                    pass
                
                if download:
                    download_path = f"temp_sitemap_{int(time.time())}.xml"
                    download.save_as(download_path)
                else:
                    content = page.content()
                    if content.startswith('<?xml') or '<urlset' in content or '<sitemapindex' in content:
                        download_path = f"temp_sitemap_{int(time.time())}.xml"
                        with open(download_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    else:
                        browser.close()
                        return None
                
                browser.close()
                
                if download_path and os.path.exists(download_path):
                    with open(download_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    os.remove(download_path)
                    self.logger.info(f"Successfully fetched sitemap: {url}")
                    return content
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to fetch sitemap {url}: {str(e)}")
            if download_path and os.path.exists(download_path):
                os.remove(download_path)
            return None
    
    def filter_2025_sitemaps(self, xml_content):
        """Filter sitemaps containing 2025 posts."""
        root = ET.fromstring(xml_content)
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        filtered = []
        for sitemap in root.findall('.//ns:sitemap', ns):
            loc = sitemap.find('ns:loc', ns)
            if loc is not None:
                url = loc.text
                if 'posts/2025/posts-2025' in url:
                    filtered.append(url)
        
        self.logger.info(f"Filtered {len(filtered)} sitemaps containing 2025 posts")
        return filtered
    
    def extract_article_urls(self, xml_content):
        """Extract article URLs from sitemap."""
        root = ET.fromstring(xml_content)
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        urls = []
        for url_elem in root.findall('.//ns:url', ns):
            loc = url_elem.find('ns:loc', ns)
            if loc is not None:
                urls.append(loc.text)
        
        return urls
    
    def filter_interview_urls(self, urls):
        """Filter URLs containing 'interview-experience'."""
        interview_urls = []
        for url in urls:
            if 'interview-experience' in url.lower():
                interview_urls.append(url)
        
        if interview_urls:
            self.logger.info(f"Found {len(interview_urls)} interview URLs in sitemap")
        return interview_urls
    
    # ========================================================================
    # SCRAPING METHODS
    # ========================================================================
    
    def fetch_html(self, url):
        """Fetch HTML using Playwright to avoid bot detection."""
        try:
            random_delay(2, 5)
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York',
                )
                
                page = context.new_page()
                response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
                
                if response.status >= 400:
                    browser.close()
                    
                    if response.status == 404:
                        return None, "HTTP_404_NOT_FOUND"
                    elif response.status == 410:
                        return None, "HTTP_410_GONE (Deleted or account suspended)"
                    elif response.status == 403:
                        return None, "HTTP_403_FORBIDDEN (Access denied/rate limited)"
                    elif response.status == 429:
                        self.logger.warning(f"Rate limited! Sleeping for 30 seconds...")
                        time.sleep(30)
                        return None, "HTTP_429_TOO_MANY_REQUESTS (Rate limited)"
                    elif response.status >= 500:
                        return None, f"HTTP_{response.status}_SERVER_ERROR"
                    else:
                        return None, f"HTTP_{response.status}_ERROR"
                
                random_delay(1, 3)
                html = page.content()
                browser.close()
                
                self.logger.info(f"Successfully fetched with Playwright: {url}")
                return html, None
        
        except Exception as e:
            error_type = str(e)
            
            if "Timeout" in error_type or "timeout" in error_type:
                self.logger.warning(f"Timeout for {url}")
                return None, "TIMEOUT (Request took too long)"
            elif "net::ERR" in error_type:
                self.logger.warning(f"Connection error for {url}")
                return None, "CONNECTION_ERROR (Network issue)"
            else:
                self.logger.error(f"Playwright error for {url}: {str(e)}")
                return None, f"PLAYWRIGHT_ERROR: {str(e)}"
    
    def is_paywalled(self, soup):
        """Robust paywall detection with enhanced Apollo State checking."""
        
        # 1. Check for "meteredContent" class
        if soup.find("article", {"class": re.compile(r".*meteredContent.*", re.I)}):
            return True, "meteredContent class"
        
        # 2. Check for "Member-only story" badge
        if soup.find(string=re.compile(r"Member-only story", re.I)):
            return True, "Member-only badge"
        
        # 3. Check JSON-LD schema
        json_ld = soup.find("script", {"type": "application/ld+json"})
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                if data.get("isAccessibleForFree") == False:
                    return True, "JSON-LD isAccessibleForFree"
            except (json.JSONDecodeError, Exception):
                pass
        
        # 4. Check Apollo state - ENHANCED
        apollo_state = soup.find("script", string=re.compile(r"__APOLLO_STATE__", re.I))
        if apollo_state:
            try:
                json_str = apollo_state.string.split("=", 1)[1].strip()
                if json_str.endswith(";"):
                    json_str = json_str[:-1]
                
                data = json.loads(json_str)
                
                for key, value in data.items():
                    if key.startswith("Post:") and isinstance(value, dict):
                        if value.get("isLocked") == True:
                            return True, "Apollo isLocked"
                        if value.get("isLockedPreviewOnly") == True:
                            return True, "Apollo isLockedPreviewOnly"
                        if value.get("isMarkedPaywallOnly") == True:
                            return True, "Apollo isMarkedPaywallOnly"
                        
                        content_key = 'content({"postMeteringOptions":{"referrer":""}})'
                        content_ref = value.get(content_key) or value.get("content")
                        if isinstance(content_ref, dict):
                            if content_ref.get("isLockedPreviewOnly") == True:
                                return True, "Apollo content isLockedPreviewOnly"
            except (json.JSONDecodeError, Exception):
                pass
        
        # 5. Check for preview text
        if soup.find(string=re.compile(r"This is a preview", re.I)):
            return True, "Preview text"
        
        # 6. Check for paywall CTAs
        if soup.find(string=re.compile(r"Upgrade to continue|Subscribe to read", re.I)):
            return True, "Paywall CTA"
        
        return False, None
    
    def extract_metadata(self, soup, url):
        """Extract all available metadata from Medium article."""
        metadata = {}
        
        # Extract description
        desc_meta = soup.find("meta", property="og:description") or soup.find("meta", {"name": "description"})
        if desc_meta:
            metadata["description"] = desc_meta.get("content", "")
        
        # Extract reading time
        read_time_meta = soup.find("meta", {"name": "twitter:data1"})
        if read_time_meta:
            metadata["reading_time"] = read_time_meta.get("content", "")
        
        # Extract tags from Apollo State
        tags = []
        apollo_script = soup.find("script", string=re.compile(r"__APOLLO_STATE__", re.I))
        if apollo_script:
            try:
                json_str = apollo_script.string.split("=", 1)[1].strip()
                if json_str.endswith(";"):
                    json_str = json_str[:-1]
                
                data = json.loads(json_str)
                
                for key, value in data.items():
                    if key.startswith("Tag:") and isinstance(value, dict):
                        tag_title = value.get("displayTitle") or value.get("id")
                        if tag_title and tag_title not in tags:
                            tags.append(tag_title)
                
                if tags:
                    metadata["tags"] = tags
            except (json.JSONDecodeError, Exception) as e:
                self.logger.warning(f"  Failed to extract tags from Apollo state: {str(e)}")
        
        # Extract image
        image_meta = soup.find("meta", property="og:image")
        if image_meta:
            metadata["featured_image"] = image_meta.get("content", "")
        
        # Extract canonical URL
        canonical = soup.find("link", rel="canonical")
        if canonical:
            metadata["canonical_url"] = canonical.get("href", "")
        
        return metadata
    
    def extract_from_apollo_state(self, soup):
        """Extract article content from Medium's Apollo GraphQL state."""
        try:
            apollo_script = soup.find("script", string=re.compile(r"__APOLLO_STATE__", re.I))
            
            if not apollo_script:
                return None
            
            json_str = apollo_script.string.split("=", 1)[1].strip()
            if json_str.endswith(";"):
                json_str = json_str[:-1]
            
            data = json.loads(json_str)
            
            paragraphs = []
            for key, value in data.items():
                if key.startswith("Paragraph:") and isinstance(value, dict):
                    text = value.get("text", "")
                    paragraph_type = value.get("type", "P")
                    
                    if text.strip():
                        try:
                            index = int(key.split("_")[-1])
                        except (ValueError, IndexError):
                            index = 0
                        
                        paragraphs.append({
                            "index": index,
                            "text": text,
                            "type": paragraph_type
                        })
            
            if not paragraphs:
                return None
            
            paragraphs.sort(key=lambda x: x["index"])
            
            markdown_content = []
            for para in paragraphs:
                text = para["text"]
                para_type = para["type"]
                
                if para_type == "H2":
                    markdown_content.append(f"## {text}")
                elif para_type == "H3":
                    markdown_content.append(f"### {text}")
                elif para_type == "H4":
                    markdown_content.append(f"#### {text}")
                elif para_type == "PQ":
                    markdown_content.append(f"> {text}")
                elif para_type == "PRE":
                    markdown_content.append(f"```\n{text}\n```")
                elif para_type in ["OLI", "ULI"]:
                    markdown_content.append(f"- {text}")
                else:
                    markdown_content.append(text)
            
            content = "\n\n".join(markdown_content)
            
            self.logger.info(f"Extracted {len(paragraphs)} paragraphs from Apollo state")
            return content
        
        except Exception as e:
            self.logger.warning(f"Failed to extract from Apollo state: {str(e)}")
            return None
    
    def parse_article(self, html, url):
        """Parse Medium article with Apollo State + HTML fallback."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # Check for paywall FIRST
            is_paywalled_result, paywall_reason = self.is_paywalled(soup)
            if is_paywalled_result:
                self.logger.info(f"Paywalled article skipped: {url} - {paywall_reason}")
                return None, f"PAYWALLED ({paywall_reason})"
            
            # Extract title
            title_meta = soup.find("meta", property="og:title")
            title = title_meta["content"] if title_meta else "Untitled"
            
            # Extract published date
            date_meta = soup.find("meta", property="article:published_time")
            published_at = date_meta["content"] if date_meta else None
            
            # Try Apollo State FIRST
            raw_content = self.extract_from_apollo_state(soup)
            extraction_method = "Apollo State"
            
            if not raw_content or len(raw_content) < 100:
                self.logger.info(f"Apollo extraction insufficient, trying HTML strategies")
                
                article_tag = None
                
                # Strategy 1: Standard <article> tag
                article_tag = soup.find("article")
                if article_tag:
                    extraction_method = "Article tag"
                
                # Strategy 2: postArticle class
                if not article_tag:
                    article_tag = soup.find("div", {"class": re.compile(r".*postArticle.*", re.I)})
                    if article_tag:
                        extraction_method = "postArticle class"
                
                # Strategy 3: Main content div
                if not article_tag:
                    article_tag = soup.find("main") or soup.find("div", {"role": "main"})
                    if article_tag:
                        extraction_method = "Main tag"
                
                # Strategy 4: data-testid
                if not article_tag:
                    article_tag = soup.find("div", {"data-testid": re.compile(r".*content.*|.*article.*", re.I)})
                    if article_tag:
                        extraction_method = "data-testid"
                
                # Strategy 5: Paragraph extraction
                if not article_tag:
                    all_paragraphs = soup.find_all("p")
                    meaningful_paragraphs = [p for p in all_paragraphs 
                                            if len(p.get_text(strip=True)) > 15]
                    
                    if len(meaningful_paragraphs) >= 2:
                        article_tag = soup.new_tag("div")
                        for p in meaningful_paragraphs:
                            article_tag.append(p)
                        extraction_method = f"Paragraph extraction ({len(meaningful_paragraphs)} paras)"
                        self.logger.info(extraction_method)
                    else:
                        self.logger.warning(f"No content found - DROPPING")
                        self.logger.warning(f"  Title: {title}")
                        self.logger.warning(f"  Total <p> tags: {len(all_paragraphs)}")
                        self.logger.warning(f"  Meaningful paragraphs: {len(meaningful_paragraphs)}")
                        return None, "NO_CONTENT"
                
                raw_content = md(str(article_tag)).strip()
            
            # Validate content length
            if len(raw_content) < 100:
                self.logger.warning(f"Content too short: {len(raw_content)} chars - DROPPING")
                self.logger.warning(f"  Title: {title}")
                self.logger.warning(f"  Method: {extraction_method}")
                return None, "CONTENT_TOO_SHORT"
            
            # Extract metadata
            source_metadata = self.extract_metadata(soup, url)
            
            # Generate IDs
            document_id = generate_document_id(url)
            content_hash = generate_content_hash(title, raw_content)
            scraped_at = datetime.now(timezone.utc).isoformat()
            
            self.logger.info(f"Successfully parsed: {title}")
            self.logger.info(f"   Method: {extraction_method}, Length: {len(raw_content)} chars")
            
            article_data = {
                "document_id": document_id,
                "source_platform": "medium",
                "source_url": url,
                "title": title,
                "raw_content": raw_content,
                "content_hash": content_hash,
                "published_at": published_at,
                "scraped_at": scraped_at,
                "source_metadata": source_metadata
            }
            
            return article_data, None
            
        except Exception as e:
            self.logger.error(f"Parse error for {url}: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None, f"PARSE_ERROR: {str(e)}"
    
    def save_article(self, article):
        """Save article to a single JSON file (append mode)."""
        try:
            json_path = self.output_dir / "articles.json"
            
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    try:
                        articles_list = json.load(f)
                    except json.JSONDecodeError:
                        articles_list = []
            else:
                articles_list = []
            
            articles_list.append(article)
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(articles_list, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Saved article to JSON: {article['title']}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to save article: {str(e)}")
            return False
    
    def scrape_article(self, url):
        """Scrape a single article ethically."""
        
        # Fetch HTML
        html, fetch_error = self.fetch_html(url)
        
        if fetch_error:
            return {
                "url": url,
                "status": "FETCH_ERROR",
                "error_type": fetch_error,
                "scraped_at": datetime.now(timezone.utc).isoformat()
            }
        
        # Parse article
        article, parse_error = self.parse_article(html, url)
        
        if parse_error:
            return {
                "url": url,
                "status": "PARSE_ERROR",
                "error_type": parse_error,
                "scraped_at": datetime.now(timezone.utc).isoformat()
            }
        
        # Save to JSON
        self.save_article(article)
        
        article["status"] = "SUCCESS"
        return article
    
    # ========================================================================
    # WORKFLOW METHODS
    # ========================================================================
    
    def collect_interview_urls(self, sitemap_urls):
        """Collect all interview URLs from sitemaps."""
        self.logger.info("="*60)
        self.logger.info("PHASE 1: COLLECTING INTERVIEW URLS")
        self.logger.info("="*60)
        
        all_interview_urls = []
        
        for i, sitemap_url in enumerate(sitemap_urls, 1):
            self.logger.info(f"Processing sitemap {i}/{len(sitemap_urls)}: {sitemap_url}")
            
            sitemap_content = self.fetch_sitemap(sitemap_url)
            if sitemap_content is None:
                continue
            
            article_urls = self.extract_article_urls(sitemap_content)
            interview_urls = self.filter_interview_urls(article_urls)
            all_interview_urls.extend(interview_urls)
            
            time.sleep(1)
        
        self.logger.info(f"Total interview URLs collected: {len(all_interview_urls)}")
        
        # Save URLs to file
        urls_file = self.output_dir / 'medium_interview_urls.txt'
        with open(urls_file, 'w') as f:
            for url in all_interview_urls:
                f.write(url + '\n')
        self.logger.info(f"URLs saved to {urls_file}")
        
        return all_interview_urls
    
    def scrape_all_articles(self, urls):
        """Scrape all articles and update stats."""
        self.logger.info("="*60)
        self.logger.info("PHASE 2: SCRAPING ARTICLES")
        self.logger.info("="*60)
        self.logger.info("Using random delays (2-5s fetch, 3-8s between articles)")
        
        for idx, url in enumerate(urls, 1):
            self.logger.info(f"Scraping {idx}/{len(urls)}: {url}")
            
            result = self.scrape_article(url)
            self._update_stats(result)
            
            random_delay(3, 8)
    
    def _update_stats(self, result):
        """Update statistics based on scrape result."""
        if result.get("status") == "SUCCESS":
            self.stats["success"] += 1
        
        elif result.get("status") == "PARSE_ERROR":
            error_type = result.get("error_type", "")
            
            if "PAYWALLED" in error_type:
                self.stats["paywalled"] += 1
            else:
                self.stats["errors"]["parse_error"] += 1
        
        elif result.get("status") == "FETCH_ERROR":
            error_type = result.get("error_type", "")
            category, _ = categorize_error(error_type)
            self.stats["errors"][category] += 1
        
        else:
            self.stats["errors"]["other"] += 1
    
    def print_summary(self):
        """Print final statistics."""
        self.logger.info("="*60)
        self.logger.info("SCRAPING COMPLETE - FINAL STATISTICS")
        self.logger.info("="*60)
        self.logger.info(f"Total URLs:           {self.stats['total']}")
        self.logger.info(f"Successfully scraped: {self.stats['success']}")
        self.logger.info(f"Paywalled (skipped):  {self.stats['paywalled']}")
        self.logger.info("")
        self.logger.info("Error Breakdown:")
        self.logger.info(f"  410 Gone (deleted):      {self.stats['errors']['http_410_gone']}")
        self.logger.info(f"  404 Not Found:           {self.stats['errors']['http_404_not_found']}")
        self.logger.info(f"  403 Forbidden:           {self.stats['errors']['http_403_forbidden']}")
        self.logger.info(f"  429 Rate Limited:        {self.stats['errors']['http_429_rate_limited']}")
        self.logger.info(f"  5xx Server Errors:       {self.stats['errors']['http_5xx_server_error']}")
        self.logger.info(f"  Timeout:                 {self.stats['errors']['timeout']}")
        self.logger.info(f"  Connection Error:        {self.stats['errors']['connection_error']}")
        self.logger.info(f"  Parse Error:             {self.stats['errors']['parse_error']}")
        self.logger.info(f"  Other:                   {self.stats['errors']['other']}")
        self.logger.info("")
        self.logger.info(f"Total Failed:         {sum(self.stats['errors'].values())}")
        self.logger.info("")
        self.logger.info(f"Output file: {self.output_dir}/articles.json")
        self.logger.info(f"Log file:    {self.log_file}")
        self.logger.info("="*60)
        
        # Console output
        print("\n" + "="*60)
        print("SCRAPING COMPLETE")
        print("="*60)
        print(f"Successfully scraped: {self.stats['success']}/{self.stats['total']} articles")
        print(f"Paywalled (skipped):  {self.stats['paywalled']}")
        print(f"Failed:               {sum(self.stats['errors'].values())}")
        
        if self.stats['errors']['http_403_forbidden'] > 0:
            print(f"\nWARNING: {self.stats['errors']['http_403_forbidden']} articles blocked (403)")
        
        print(f"\nOutput: {self.output_dir}/articles.json")
        print(f"Full details in: {self.log_file}")
        print("="*60)
    
    # ========================================================================
    # MAIN RUN METHOD
    # ========================================================================
    
    def run(self):
        """Main pipeline execution."""
        self.logger.info("="*60)
        self.logger.info("MEDIUM SCRAPER - ENHANCED WITH APOLLO STATE EXTRACTION")
        self.logger.info("="*60)
        self.logger.info("Features: Apollo State parsing, improved paywall detection, tag extraction")
        
        # Fetch main sitemap
        self.logger.info("Fetching main sitemap...")
        xml_content = self.fetch_sitemap("https://medium.com/sitemap/sitemap.xml")
        if xml_content is None:
            self.logger.error("Failed to fetch main sitemap. Exiting.")
            print("ERROR: Failed to fetch main sitemap. Check scraper_log.txt for details.")
            return
        
        # Filter 2025 sitemaps
        sitemap_urls = self.filter_2025_sitemaps(xml_content)
        
        # Uncomment to test with fewer sitemaps
        sitemap_urls = sitemap_urls[:20]
        # self.logger.info(f"Running in TEST MODE - processing first 20 sitemaps")
        
        # Collect interview URLs
        interview_urls = self.collect_interview_urls(sitemap_urls)
        self.stats["total"] = len(interview_urls)
        
        # Scrape all articles
        self.scrape_all_articles(interview_urls)
        
        # Print summary
        self.print_summary()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point for the scraper."""
    # Get project root
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir
    while project_root != project_root.parent:
        if (project_root / "requirements.txt").exists() or \
           (project_root / ".git").exists() or \
           (project_root / "src").exists():
            break
        project_root = project_root.parent
    
    output_dir = project_root / "data"
    
    # Create and run scraper
    scraper = MediumScraper(output_dir)
    scraper.run()


if __name__ == "__main__":
    main()