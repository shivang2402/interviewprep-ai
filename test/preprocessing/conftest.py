"""
Shared fixtures for preprocessing step tests.
Provides base raw docs and fully-pipelined docs at each stage.
"""
import pytest


# ── Raw scraper doc (input to Step 1) ──

@pytest.fixture
def raw_doc():
    return {
        "document_id": "leetcode_abc123",
        "source_platform": "leetcode",
        "source_url": "https://leetcode.com/discuss/post/123/google-sde2-interview",
        "title": "Google SDE2 Interview Experience",
        "raw_content": (
            "I recently interviewed at Google for the SDE2 role. "
            "There were 5 rounds total. Round 1 was a phone screen with DSA questions. "
            "Round 2 was a system design round. Round 3 was a behavioral round. "
            "Round 4 and Round 5 were onsite coding rounds. "
            "I was asked about dynamic programming, graphs, and system design. "
            "The interviewer was very friendly. I got the offer after 2 weeks. "
            "Overall it was a medium difficulty interview process. "
            "My email is test@example.com and my phone is +91-9876543210."
        ),
        "published_at": "2026-01-15T10:00:00Z",
        "scraped_at": "2026-01-16T08:00:00Z",
        "scrape_type": "bulk",
        "scrape_batch_id": "2026-01-16_bulk",
        "source_metadata": {"tags": ["Interview"], "company": "Google"},
        "content_hash": "deadbeef" * 8,
    }


@pytest.fixture
def raw_doc_gfg():
    return {
        "document_id": "gfg_def456",
        "source_platform": "gfg",
        "source_url": "https://www.geeksforgeeks.org/amazon-interview-experience/",
        "title": "Amazon SDE1 Interview Experience",
        "raw_content": (
            "I applied for SDE1 at Amazon through a referral. "
            "The process had 4 rounds. Round 1 was an online assessment. "
            "Round 2 was a technical phone screen. Round 3 was a system design. "
            "Round 4 was a bar raiser behavioral round. "
            "Topics covered: arrays, trees, dynamic programming, and leadership principles. "
            "I received an offer after 3 weeks. The difficulty was medium to hard. "
            "Contact me at candidate@gmail.com for more details."
        ),
        "published_at": "2026-01-10T10:00:00Z",
        "scraped_at": "2026-01-11T08:00:00Z",
        "scrape_type": "bulk",
        "scrape_batch_id": "2026-01-11_bulk",
        "source_metadata": {"tags": ["Interview Experiences"]},
        "content_hash": "cafebabe" * 8,
    }


@pytest.fixture
def raw_doc_empty_content():
    return {
        "document_id": "leetcode_empty",
        "source_platform": "leetcode",
        "source_url": "https://leetcode.com/discuss/post/999/empty",
        "title": "Empty Post",
        "raw_content": "   ",
        "published_at": None,
        "scraped_at": "2026-01-16T08:00:00Z",
        "scrape_type": "bulk",
        "scrape_batch_id": "2026-01-16_bulk",
        "source_metadata": {},
        "content_hash": "0" * 64,
    }


# ── Doc after Step 1 (ContentNormalizer output) ──

@pytest.fixture
def normalized_doc(raw_doc):
    doc = raw_doc.copy()
    doc["preprocessing"] = {
        "content_normalizer": {
            "content": (
                "I recently interviewed at Google for the SDE2 role. "
                "There were 5 rounds total. Round 1 was a phone screen with DSA questions. "
                "Round 2 was a system design round. Round 3 was a behavioral round. "
                "Round 4 and Round 5 were onsite coding rounds. "
                "I was asked about dynamic programming, graphs, and system design. "
                "The interviewer was very friendly. I got the offer after 2 weeks. "
                "Overall it was a medium difficulty interview process. "
                "My email is test@example.com and my phone is +91-9876543210."
            ),
            "title": "Google SDE2 Interview Experience",
            "word_count": 95,
            "completed": True,
        }
    }
    return doc


# ── Doc after Step 2 (PIIRemover output) ──

@pytest.fixture
def pii_removed_doc(normalized_doc):
    doc = normalized_doc.copy()
    doc["preprocessing"] = normalized_doc["preprocessing"].copy()
    doc["preprocessing"]["pii_remover"] = {
        "content": (
            "I recently interviewed at Google for the SDE2 role. "
            "There were 5 rounds total. Round 1 was a phone screen with DSA questions. "
            "Round 2 was a system design round. Round 3 was a behavioral round. "
            "Round 4 and Round 5 were onsite coding rounds. "
            "I was asked about dynamic programming, graphs, and system design. "
            "The interviewer was very friendly. I got the offer after 2 weeks. "
            "Overall it was a medium difficulty interview process. "
            "My email is [EMAIL] and my phone is [PHONE]."
        ),
        "title": "Google SDE2 Interview Experience",
        "pii_counts": {"email": 1, "phone": 1},
        "completed": True,
    }
    return doc


# ── Doc after Step 3 (QualityFilter output) ──

@pytest.fixture
def quality_passed_doc(pii_removed_doc):
    doc = pii_removed_doc.copy()
    doc["preprocessing"] = pii_removed_doc["preprocessing"].copy()
    doc["preprocessing"]["quality_filter"] = {
        "quality_score": 0.85,
        "completed": True,
    }
    return doc


# ── Doc after Step 4 (Deduplicator output) ──

@pytest.fixture
def deduped_doc(quality_passed_doc):
    doc = quality_passed_doc.copy()
    doc["preprocessing"] = quality_passed_doc["preprocessing"].copy()
    doc["preprocessing"]["deduplicator"] = {
        "content_hash": "a" * 64,
        "completed": True,
    }
    return doc


# ── Doc after Step 5 (EntityExtractor output) ──

@pytest.fixture
def entity_extracted_doc(deduped_doc):
    doc = deduped_doc.copy()
    doc["preprocessing"] = deduped_doc["preprocessing"].copy()
    doc["preprocessing"]["entity_extractor"] = {
        "company": "Google",
        "role": "Software Development Engineer",
        "experience_level": "mid",
        "interview_types": ["phone_screen", "onsite"],
        "num_rounds": 5,
        "topics": ["behavioral", "dsa", "system_design"],
        "interview_outcome": "offer",
        "difficulty": "medium",
        "completed": True,
    }
    return doc


# ── Minimal valid kwargs for ProcessedInterviewDocument ──

@pytest.fixture
def valid_processed_kwargs():
    return {
        "document_id": "leetcode_abc123",
        "source_platform": "leetcode",
        "source_url": "https://leetcode.com/discuss/post/123/google-sde2-interview",
        "content_hash": "a" * 64,
        "title": "Google SDE2 Interview Experience",
        "content": "I recently interviewed at Google. There were 5 rounds.",
        "word_count": 10,
        "company": "Google",
        "role": "Software Development Engineer",
        "experience_level": "mid",
        "interview_outcome": "offer",
        "difficulty": "medium",
        "num_rounds": 5,
        "interview_types": ["phone_screen", "onsite"],
        "topics": ["dsa", "system_design"],
        "published_at": "2026-01-15T10:00:00Z",
        "scraped_at": "2026-01-16T08:00:00Z",
        "scrape_batch_id": "2026-01-16_bulk",
        "source_metadata": {},
    }