# InterviewPrep AI

```
{
// ─────────── Identity & Traceability ───────────
"document_id": "reddit_abc123def",  //platform_id 
"source_platform": "reddit",
"source_url": "https://reddit.com/r/cscareer.../abc123",

// ─────────── Core Content ───────────
"title": "My Google L4 Interview Experience - Offer!",
"raw_content": "Full text of the post including comments...",
"content_hash": "a1b2c3d4", // Hashed, not stored later

// ─────────── Temporal Information ───────────
"published_at": "2024-01-10T14:30:00Z", // When posted
"scraped_at": "2024-01-15T02:00:00Z", // When we got it

// ─────────── Scrape Metadata ───────────
"scrape_type": "incremental", // "bulk" or "incremental"
"scrape_batch_id": "2024-01-15_weekly",

// ─────────── Source-Specific Metadata ───────────
"source_metadata": {
// Varies by platform - see below
}
}
```
