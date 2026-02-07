from playwright.sync_api import sync_playwright
import xml.etree.ElementTree as ET
import os
import time
import json
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from datetime import datetime, timezone
from pathlib import Path
import re
import logging
import hashlib
import random

# Realistic browser headers to avoid bot detection
def get_headers():
    """Return realistic browser headers."""
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(log_file):
    """Setup logging configuration."""
    
    # Create parent directory if needed
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, mode='w', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Reduce console verbosity - only show warnings and above
    console_handler = logging.getLogger().handlers[1]
    console_handler.setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

# ============================================================================
# SITEMAP FETCHING FUNCTIONS
# ============================================================================

def fetch_sitemap_with_download(url, logger):
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
                logger.info(f"Successfully fetched sitemap: {url}")
                return content
            return None
            
    except Exception as e:
        logger.error(f"Failed to fetch sitemap {url}: {str(e)}")
        if download_path and os.path.exists(download_path):
            os.remove(download_path)
        return None

def filter_2025_sitemaps(xml_content, logger):
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
    
    logger.info(f"Filtered {len(filtered)} sitemaps containing 2025 posts")
    return filtered

def extract_article_urls(xml_content):
    """Extract article URLs from sitemap."""
    root = ET.fromstring(xml_content)
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    urls = []
    for url_elem in root.findall('.//ns:url', ns):
        loc = url_elem.find('ns:loc', ns)
        if loc is not None:
            urls.append(loc.text)
    
    return urls

def filter_interview_urls(urls, logger):
    """Filter URLs containing 'interview-experience'."""
    interview_urls = []
    for url in urls:
        if 'interview-experience' in url.lower():
            interview_urls.append(url)
    
    if interview_urls:
        logger.info(f"Found {len(interview_urls)} interview URLs in sitemap")
    return interview_urls

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_document_id(url):
    """Generate document_id from URL: medium_article-slug"""
    parts = url.rstrip('/').split('/')
    slug = parts[-1] if parts else "unknown"
    return f"medium_{slug}"

def generate_content_hash(title, content):
    """Generate MD5 hash for deduplication."""
    return hashlib.md5(f"{title}{content}".encode()).hexdigest()

def random_delay(min_seconds, max_seconds):
    """Sleep for a random amount of time to mimic human behavior."""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

# ============================================================================
# SCRAPING FUNCTIONS
# ============================================================================

def fetch_html(url, logger):
    """Fetch HTML using Playwright (real browser) to avoid bot detection."""
    try:
        # Random delay before request (2-5 seconds)
        random_delay(2, 5)
        
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(headless=True)
            
            # Create context with realistic settings
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
            )
            
            # Create new page
            page = context.new_page()
            
            # Navigate to URL
            response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # Check for HTTP errors
            if response.status >= 400:
                browser.close()
                
                if response.status == 404:
                    return None, "HTTP_404_NOT_FOUND"
                elif response.status == 410:
                    return None, "HTTP_410_GONE (Deleted or account suspended)"
                elif response.status == 403:
                    return None, "HTTP_403_FORBIDDEN (Access denied/rate limited)"
                elif response.status == 429:
                    logger.warning(f"Rate limited! Sleeping for 30 seconds...")
                    time.sleep(30)
                    return None, "HTTP_429_TOO_MANY_REQUESTS (Rate limited)"
                elif response.status >= 500:
                    return None, f"HTTP_{response.status}_SERVER_ERROR"
                else:
                    return None, f"HTTP_{response.status}_ERROR"
            
            # Wait a bit for dynamic content to load (simulate human reading)
            random_delay(1, 3)
            
            # Get page content
            html = page.content()
            
            # Close browser
            browser.close()
            
            logger.info(f"Successfully fetched with Playwright: {url}")
            return html, None
    
    except Exception as e:
        error_type = str(e)
        
        # Categorize Playwright-specific errors
        if "Timeout" in error_type or "timeout" in error_type:
            logger.warning(f"Timeout for {url}")
            return None, "TIMEOUT (Request took too long)"
        elif "net::ERR" in error_type:
            logger.warning(f"Connection error for {url}")
            return None, "CONNECTION_ERROR (Network issue)"
        else:
            logger.error(f"Playwright error for {url}: {str(e)}")
            return None, f"PLAYWRIGHT_ERROR: {str(e)}"

def is_paywalled(soup):
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
            
            # Check ALL Post objects, not just first one
            for key, value in data.items():
                if key.startswith("Post:") and isinstance(value, dict):
                    # Check multiple paywall indicators
                    if value.get("isLocked") == True:
                        return True, "Apollo isLocked"
                    if value.get("isLockedPreviewOnly") == True:
                        return True, "Apollo isLockedPreviewOnly"
                    if value.get("isMarkedPaywallOnly") == True:
                        return True, "Apollo isMarkedPaywallOnly"
                    
                    # Check content object for locked status
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

def extract_metadata(soup, url, logger):
    """Extract all available metadata from Medium article including tags from Apollo State."""
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
            
            # Find all Tag objects in Apollo state
            for key, value in data.items():
                if key.startswith("Tag:") and isinstance(value, dict):
                    tag_title = value.get("displayTitle") or value.get("id")
                    if tag_title and tag_title not in tags:
                        tags.append(tag_title)
            
            if tags:
                metadata["tags"] = tags
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"  Failed to extract tags from Apollo state: {str(e)}")
            
    # Extract image
    image_meta = soup.find("meta", property="og:image")
    if image_meta:
        metadata["featured_image"] = image_meta.get("content", "")
    
    # Extract canonical URL
    canonical = soup.find("link", rel="canonical")
    if canonical:
        metadata["canonical_url"] = canonical.get("href", "")
    
    return metadata

def extract_from_apollo_state(soup, logger):
    """Extract article content from Medium's Apollo GraphQL state."""
    try:
        apollo_script = soup.find("script", string=re.compile(r"__APOLLO_STATE__", re.I))
        
        if not apollo_script:
            return None
        
        json_str = apollo_script.string.split("=", 1)[1].strip()
        if json_str.endswith(";"):
            json_str = json_str[:-1]
        
        data = json.loads(json_str)
        
        # Find all paragraph objects
        paragraphs = []
        for key, value in data.items():
            if key.startswith("Paragraph:") and isinstance(value, dict):
                text = value.get("text", "")
                paragraph_type = value.get("type", "P")
                
                if text.strip():
                    # Extract the index from the key for proper ordering
                    # Key format: "Paragraph:67db0db5c8aa_0"
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
        
        # Sort by index to maintain order
        paragraphs.sort(key=lambda x: x["index"])
        
        # Convert to markdown
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
            elif para_type == "PQ":  # Pull quote
                markdown_content.append(f"> {text}")
            elif para_type == "PRE":  # Code block
                markdown_content.append(f"```\n{text}\n```")
            elif para_type in ["OLI", "ULI"]:  # List items
                markdown_content.append(f"- {text}")
            else:  # P, BQ, etc.
                markdown_content.append(text)
        
        content = "\n\n".join(markdown_content)
        
        logger.info(f"Extracted {len(paragraphs)} paragraphs from Apollo state")
        return content
    
    except Exception as e:
        logger.warning(f"Failed to extract from Apollo state: {str(e)}")
        return None

def parse_medium_article(html, url, logger):
    """Parse Medium article with Apollo State + HTML fallback."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Check for paywall FIRST (improved detection)
        is_paywalled_result, paywall_reason = is_paywalled(soup)
        if is_paywalled_result:
            logger.info(f"Paywalled article skipped: {url} - {paywall_reason}")
            return None, f"PAYWALLED ({paywall_reason})"
        
        # Extract title
        title_meta = soup.find("meta", property="og:title")
        title = title_meta["content"] if title_meta else "Untitled"
        
        # Extract published date
        date_meta = soup.find("meta", property="article:published_time")
        published_at = date_meta["content"] if date_meta else None
        
        # ===== STRATEGY 0: Try Apollo State FIRST =====
        raw_content = extract_from_apollo_state(soup, logger)
        extraction_method = "Apollo State"
        
        if not raw_content or len(raw_content) < 100:
            # Fall back to HTML parsing
            logger.info(f"Apollo extraction insufficient, trying HTML strategies")
            
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
            
            # Strategy 5: Paragraph extraction (relaxed)
            if not article_tag:
                all_paragraphs = soup.find_all("p")
                meaningful_paragraphs = [p for p in all_paragraphs 
                                        if len(p.get_text(strip=True)) > 15]
                
                if len(meaningful_paragraphs) >= 2:
                    article_tag = soup.new_tag("div")
                    for p in meaningful_paragraphs:
                        article_tag.append(p)
                    extraction_method = f"Paragraph extraction ({len(meaningful_paragraphs)} paras)"
                    logger.info(extraction_method)
                else:
                    logger.warning(f"No content found - DROPPING")
                    logger.warning(f"  Title: {title}")
                    logger.warning(f"  Total <p> tags: {len(all_paragraphs)}")
                    logger.warning(f"  Meaningful paragraphs: {len(meaningful_paragraphs)}")
                    return None, "NO_CONTENT"
            
            # Convert to markdown
            raw_content = md(str(article_tag)).strip()
        
        # Validate content length
        if len(raw_content) < 100:
            logger.warning(f"Content too short: {len(raw_content)} chars - DROPPING")
            logger.warning(f"  Title: {title}")
            logger.warning(f"  Method: {extraction_method}")
            return None, "CONTENT_TOO_SHORT"
        
        # Extract metadata
        source_metadata = extract_metadata(soup, url, logger)
        
        # Generate IDs
        document_id = generate_document_id(url)
        content_hash = generate_content_hash(title, raw_content)
        scraped_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"Successfully parsed: {title}")
        logger.info(f"   Method: {extraction_method}, Length: {len(raw_content)} chars")
        
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
        logger.error(f"Parse error for {url}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())  # Full stack trace for debugging
        return None, f"PARSE_ERROR: {str(e)}"

# ============================================================================
# SAVE FUNCTIONS
# ============================================================================

def save_article_to_json(article, output_dir, logger):
    """Save article to a single JSON file (append mode)."""
    try:
        outdir = Path(output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        
        json_path = outdir / "articles.json"
        
        # Load existing data or create new list
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                try:
                    articles_list = json.load(f)
                except json.JSONDecodeError:
                    articles_list = []
        else:
            articles_list = []
        
        # Append new article
        articles_list.append(article)
        
        # Save back to file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(articles_list, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved article to JSON: {article['title']}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to save article: {str(e)}")
        return False

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def categorize_error(error_type):
    """Helper to categorize error types."""
    if "410" in error_type:
        return "http_410_gone", "410 GONE - Article deleted or account suspended"
    elif "404" in error_type:
        return "http_404_not_found", "404 NOT FOUND - Article doesn't exist"
    elif "403" in error_type:
        return "http_403_forbidden", "403 FORBIDDEN - Access denied"
    elif "429" in error_type:
        return "http_429_rate_limited", "429 RATE LIMITED - Too many requests"
    elif "TIMEOUT" in error_type:
        return "timeout", "TIMEOUT - Request took too long"
    elif "CONNECTION" in error_type:
        return "connection_error", "CONNECTION ERROR - Network issue"
    elif "SERVER_ERROR" in error_type or any(str(c) in error_type for c in range(500, 600)):
        return "http_5xx_server_error", f"SERVER ERROR - {error_type}"
    else:
        return "other", f"FETCH ERROR - {error_type}"

# ============================================================================
# MAIN SCRAPING FUNCTION
# ============================================================================

def scrape_article(url, output_dir, logger):
    """Scrape a single article ethically."""
    
    # Fetch HTML with detailed error
    html, fetch_error = fetch_html(url, logger)
    
    if fetch_error:
        return {
            "url": url,
            "status": "FETCH_ERROR",
            "error_type": fetch_error,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
    
    # Parse article
    article, parse_error = parse_medium_article(html, url, logger)
    
    if parse_error:
        return {
            "url": url,
            "status": "PARSE_ERROR",
            "error_type": parse_error,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
    
    # Save to JSON
    save_article_to_json(article, output_dir, logger)
    
    # Mark as success
    article["status"] = "SUCCESS"
    return article

# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    # Get project root - go up until we find a marker file (like requirements.txt or .git)
    script_dir = Path(__file__).resolve().parent  # src/scrapers/
    
    # Try to find project root by looking for common markers
    project_root = script_dir
    while project_root != project_root.parent:  # Stop at filesystem root
        if (project_root / "requirements.txt").exists() or \
           (project_root / ".git").exists() or \
           (project_root / "src").exists():
            break
        project_root = project_root.parent
    
    output_dir = project_root / "data"
    log_file = output_dir / "medium_scraper_log.txt"
    
    # Setup logging
    logger = setup_logging(log_file)
    
    # Create output directory
    output_dir.mkdir(exist_ok=True)
    
    logger.info("="*60)
    logger.info("MEDIUM SCRAPER - ENHANCED WITH APOLLO STATE EXTRACTION")
    logger.info("="*60)
    logger.info("Features: Apollo State parsing, improved paywall detection, tag extraction")
    
    # Fetch main sitemap
    logger.info("Fetching main sitemap...")
    xml_content = fetch_sitemap_with_download("https://medium.com/sitemap/sitemap.xml", logger)
    if xml_content is None:
        logger.error("Failed to fetch main sitemap. Exiting.")
        print("ERROR: Failed to fetch main sitemap. Check scraper_log.txt for details.")
        return
    
    # Filter 2025 sitemaps
    sitemap_urls = filter_2025_sitemaps(xml_content, logger)
    
    #uncomment this line to test with fewer sitemaps
    # sitemap_urls = sitemap_urls[:20]
    # logger.info(f"Running in TEST MODE - processing first 20 sitemaps")
    
    # Step 1: Collect all interview URLs
    logger.info("="*60)
    logger.info("PHASE 1: COLLECTING INTERVIEW URLS")
    logger.info("="*60)
    
    all_interview_urls = []
    
    for i, sitemap_url in enumerate(sitemap_urls, 1):
        logger.info(f"Processing sitemap {i}/{len(sitemap_urls)}: {sitemap_url}")
        
        sitemap_content = fetch_sitemap_with_download(sitemap_url, logger)
        if sitemap_content is None:
            continue
        
        article_urls = extract_article_urls(sitemap_content)
        interview_urls = filter_interview_urls(article_urls, logger)
        all_interview_urls.extend(interview_urls)
        
        # Small delay between sitemap fetches
        time.sleep(1)
    
    logger.info(f"Total interview URLs collected: {len(all_interview_urls)}")
    
    # Save URLs to file
    urls_file = output_dir / 'medium_interview_urls.txt'
    with open(urls_file, 'w') as f:
        for url in all_interview_urls:
            f.write(url + '\n')
    logger.info(f"URLs saved to {urls_file}")
    
    # Step 2: Scrape each article
    logger.info("="*60)
    logger.info("PHASE 2: SCRAPING ARTICLES")
    logger.info("="*60)
    logger.info("Using random delays (2-5s fetch, 3-8s between articles)")
    
    stats = {
        "total": len(all_interview_urls),
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
    
    for idx, url in enumerate(all_interview_urls, 1):
        logger.info(f"Scraping {idx}/{len(all_interview_urls)}: {url}")
        
        result = scrape_article(url, output_dir, logger)
        
        # Success case
        if result.get("status") == "SUCCESS":
            stats["success"] += 1
        
        # Parse errors (includes paywalled articles)
        elif result.get("status") == "PARSE_ERROR":
            error_type = result.get("error_type", "")
            
            if "PAYWALLED" in error_type:
                stats["paywalled"] += 1
            else:
                stats["errors"]["parse_error"] += 1
        
        # Fetch errors
        elif result.get("status") == "FETCH_ERROR":
            error_type = result.get("error_type", "")
            category, _ = categorize_error(error_type)
            stats["errors"][category] += 1
        
        # Unknown
        else:
            stats["errors"]["other"] += 1
        
        # Random delay between articles (3-8 seconds)
        random_delay(3, 8)
    
    # Final summary
    logger.info("="*60)
    logger.info("SCRAPING COMPLETE - FINAL STATISTICS")
    logger.info("="*60)
    logger.info(f"Total URLs:           {stats['total']}")
    logger.info(f"Successfully scraped: {stats['success']}")
    logger.info(f"Paywalled (skipped):  {stats['paywalled']}")
    logger.info("")
    logger.info("Error Breakdown:")
    logger.info(f"  410 Gone (deleted):      {stats['errors']['http_410_gone']}")
    logger.info(f"  404 Not Found:           {stats['errors']['http_404_not_found']}")
    logger.info(f"  403 Forbidden:           {stats['errors']['http_403_forbidden']}")
    logger.info(f"  429 Rate Limited:        {stats['errors']['http_429_rate_limited']}")
    logger.info(f"  5xx Server Errors:       {stats['errors']['http_5xx_server_error']}")
    logger.info(f"  Timeout:                 {stats['errors']['timeout']}")
    logger.info(f"  Connection Error:        {stats['errors']['connection_error']}")
    logger.info(f"  Parse Error:             {stats['errors']['parse_error']}")
    logger.info(f"  Other:                   {stats['errors']['other']}")
    logger.info("")
    logger.info(f"Total Failed:         {sum(stats['errors'].values())}")
    logger.info("")
    
    logger.info(f"Output file: {output_dir}/articles.json")
    logger.info(f"Log file:    {log_file}")
    logger.info(f"URLs file:   {urls_file}")
    logger.info("="*60)
    

    print("\n" + "="*60)
    print("SCRAPING COMPLETE")
    print("="*60)
    print(f"Successfully scraped: {stats['success']}/{stats['total']} articles")
    print(f"Paywalled (skipped):  {stats['paywalled']}")
    print(f"Failed:               {sum(stats['errors'].values())}")
    
    if stats['errors']['http_403_forbidden'] > 0:
        print(f"\nWARNING: {stats['errors']['http_403_forbidden']} articles blocked (403)")
    
    print(f"\nOutput: {output_dir}/articles.json")
    print(f"Full details in: {log_file}")
    print("="*60)

if __name__ == "__main__":
    main()