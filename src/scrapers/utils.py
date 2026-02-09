"""Utility functions for web scraping."""

import hashlib
import random
import time

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