"""
Tests for Step 2: PIIRemover.

Covers:
- process(): happy path, missing content, output schema
- _regex_scrub(): email, phone, personal URL detection/redaction
- pii_counts accumulation
- title scrubbing
- docs with no PII pass through cleanly
- _merge_counts() helper
"""
import pytest
from src.preprocessing.steps.pii_remover import PIIRemover, _merge_counts


@pytest.fixture
def remover():
    return PIIRemover()


def _doc_with_content(content, title="Google Interview Experience"):
    return {
        "document_id": "test_pii_doc",
        "source_platform": "leetcode",
        "preprocessing": {
            "content_normalizer": {
                "content": content,
                "title": title,
                "word_count": len(content.split()),
                "completed": True,
            }
        }
    }


# ── process() — output schema ──

class TestProcessSchema:
    def test_returns_doc_not_none(self, remover):
        doc = _doc_with_content("This is a clean interview experience about Google rounds.")
        result = remover.process(doc)
        assert result is not None

    def test_pii_remover_key_added(self, remover):
        doc = _doc_with_content("Clean content about interview rounds at Google.")
        result = remover.process(doc)
        assert "pii_remover" in result["preprocessing"]

    def test_output_has_required_fields(self, remover):
        doc = _doc_with_content("Clean content for testing output fields of pii remover step.")
        result = remover.process(doc)
        pr = result["preprocessing"]["pii_remover"]
        assert "content" in pr
        assert "title" in pr
        assert "pii_counts" in pr
        assert pr["completed"] is True

    def test_never_returns_none(self, remover):
        """PIIRemover never filters — even empty-ish content passes."""
        doc = _doc_with_content("")
        result = remover.process(doc)
        assert result is not None


# ── Email redaction ──

class TestEmailRedaction:
    def test_email_replaced_with_placeholder(self, remover):
        doc = _doc_with_content("Contact me at john.doe@gmail.com for questions.")
        result = remover.process(doc)
        content = result["preprocessing"]["pii_remover"]["content"]
        assert "john.doe@gmail.com" not in content
        assert "[EMAIL]" in content

    def test_email_counted(self, remover):
        doc = _doc_with_content("Email me at a@b.com or c@d.org please.")
        result = remover.process(doc)
        counts = result["preprocessing"]["pii_remover"]["pii_counts"]
        assert counts.get("email", 0) >= 1

    def test_multiple_emails_all_redacted(self, remover):
        doc = _doc_with_content("first@example.com and second@test.io are both emails.")
        result = remover.process(doc)
        content = result["preprocessing"]["pii_remover"]["content"]
        assert "first@example.com" not in content
        assert "second@test.io" not in content

    def test_no_false_positive_on_mention_of_email_word(self, remover):
        """The word 'email' alone should not be redacted."""
        doc = _doc_with_content("They asked me to send an email to the recruiter.")
        result = remover.process(doc)
        content = result["preprocessing"]["pii_remover"]["content"]
        assert "email" in content.lower()


# ── Phone number redaction ──

class TestPhoneRedaction:
    def test_indian_phone_replaced(self, remover):
        doc = _doc_with_content("Call me at +91-9876543210 after the interview.")
        result = remover.process(doc)
        content = result["preprocessing"]["pii_remover"]["content"]
        assert "+91-9876543210" not in content
        assert "[PHONE]" in content

    def test_phone_counted(self, remover):
        doc = _doc_with_content("My number is +91-9876543210 reach out anytime.")
        result = remover.process(doc)
        counts = result["preprocessing"]["pii_remover"]["pii_counts"]
        assert counts.get("phone", 0) >= 1


# ── Title scrubbing ──

class TestTitleScrubbing:
    def test_email_in_title_scrubbed(self, remover):
        doc = _doc_with_content(
            "Normal content about interview experience rounds at Google.",
            title="Contact user@test.com for details"
        )
        result = remover.process(doc)
        title = result["preprocessing"]["pii_remover"]["title"]
        assert "user@test.com" not in title

    def test_clean_title_unchanged(self, remover):
        doc = _doc_with_content(
            "Normal content about interview rounds.",
            title="Google SDE2 Interview Experience"
        )
        result = remover.process(doc)
        title = result["preprocessing"]["pii_remover"]["title"]
        assert title == "Google SDE2 Interview Experience"


# ── No PII case ──

class TestNoPII:
    def test_clean_doc_has_empty_pii_counts(self, remover):
        doc = _doc_with_content(
            "I interviewed at Google for SDE2. There were 5 rounds. "
            "Round 1 was DSA. I got the offer. The process was smooth."
        )
        result = remover.process(doc)
        counts = result["preprocessing"]["pii_remover"]["pii_counts"]
        assert counts == {}

    def test_clean_content_unchanged(self, remover):
        text = "I interviewed at Google for SDE2. The process had 5 rounds."
        doc = _doc_with_content(text)
        result = remover.process(doc)
        content = result["preprocessing"]["pii_remover"]["content"]
        assert content == text


# ── _regex_scrub() ──

class TestRegexScrub:
    def test_returns_tuple(self, remover):
        text, counts = remover._regex_scrub("hello world")
        assert isinstance(text, str)
        assert isinstance(counts, dict)

    def test_no_pii_empty_counts(self, remover):
        _, counts = remover._regex_scrub("no pii content here at all")
        assert counts == {}

    def test_email_in_scrub(self, remover):
        text, counts = remover._regex_scrub("Send to me@test.com please.")
        assert "me@test.com" not in text
        assert counts.get("email", 0) >= 1


# ── _merge_counts() helper ──

class TestMergeCounts:
    def test_merge_into_empty(self):
        target = {}
        _merge_counts(target, {"email": 2, "phone": 1})
        assert target == {"email": 2, "phone": 1}

    def test_merge_adds_to_existing(self):
        target = {"email": 3}
        _merge_counts(target, {"email": 2, "phone": 1})
        assert target["email"] == 5
        assert target["phone"] == 1

    def test_merge_empty_source(self):
        target = {"email": 1}
        _merge_counts(target, {})
        assert target == {"email": 1}

    def test_merge_does_not_modify_source(self):
        target = {}
        source = {"email": 1}
        _merge_counts(target, source)
        assert source == {"email": 1}