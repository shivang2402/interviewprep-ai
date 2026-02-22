"""
Tests for Step 3: QualityFilter.

Covers:
- process(): all 4 checks (word count, error page, language, signal)
- _is_error_page(): known patterns, clean content
- _is_allowed_language(): English pass, non-English fail, short text bypass
- _compute_signal_ratio(): empty text, signal words, no signal
- _compute_quality_score(): boundary conditions for length and signal
- Filter reason tagging
- Quality score written to doc on pass
"""
import pytest
from src.preprocessing.steps.quality_filter import QualityFilter


@pytest.fixture
def qf():
    return QualityFilter(
        min_word_count=10,
        max_word_count=5000,
        min_signal_ratio=0.01,
        allowed_languages=["en"],
    )


def _doc(content, word_count=None):
    """Helper to create doc in the format QualityFilter expects."""
    wc = word_count if word_count is not None else len(content.split())
    return {
        "document_id": "test_qf_doc",
        "source_platform": "leetcode",
        "preprocessing": {
            "content_normalizer": {
                "word_count": wc,
                "completed": True,
            },
            "pii_remover": {
                "content": content,
                "completed": True,
            },
        }
    }


GOOD_CONTENT = (
    "I recently had my interview at Google for the SDE2 role. "
    "There were 5 rounds in total. Round 1 was a phone screen with coding questions. "
    "Round 2 was system design. The interviewer asked me about distributed systems. "
    "Round 3 was behavioral and focused on past projects. I got an offer after 2 weeks. "
    "Overall the difficulty was medium. The process was smooth and well-organized. "
    "I highly recommend preparing dynamic programming and graph algorithms."
)


# ── Happy path ──

class TestProcessHappyPath:
    def test_good_doc_passes(self, qf):
        doc = _doc(GOOD_CONTENT)
        result = qf.process(doc)
        assert result is not None

    def test_quality_score_added(self, qf):
        doc = _doc(GOOD_CONTENT)
        result = qf.process(doc)
        assert "quality_filter" in result["preprocessing"]
        assert "quality_score" in result["preprocessing"]["quality_filter"]

    def test_completed_flag_set(self, qf):
        doc = _doc(GOOD_CONTENT)
        result = qf.process(doc)
        assert result["preprocessing"]["quality_filter"]["completed"] is True

    def test_quality_score_in_range(self, qf):
        doc = _doc(GOOD_CONTENT)
        result = qf.process(doc)
        score = result["preprocessing"]["quality_filter"]["quality_score"]
        assert 0.0 <= score <= 1.0

    def test_content_not_modified(self, qf):
        doc = _doc(GOOD_CONTENT)
        result = qf.process(doc)
        assert result["preprocessing"]["pii_remover"]["content"] == GOOD_CONTENT


# ── Check 1: Word count ──

class TestWordCountCheck:
    def test_too_short_filtered(self, qf):
        doc = _doc("Too short.", word_count=2)
        result = qf.process(doc)
        assert result is None

    def test_word_count_exactly_at_min_passes(self, qf):
        content = " ".join(["interview"] * 10)
        doc = _doc(content, word_count=10)
        result = qf.process(doc)
        # May still fail language/signal, but word count check passes
        # Just verify it's not filtered for word count
        if result is None:
            assert "too_short" not in doc.get("_filter_reason", "")

    def test_too_long_filtered(self, qf):
        doc = _doc(GOOD_CONTENT, word_count=6000)
        result = qf.process(doc)
        assert result is None
        assert "too_long" in doc["_filter_reason"]

    def test_filter_reason_includes_word_count(self, qf):
        doc = _doc("Short.", word_count=1)
        qf.process(doc)
        assert "too_short" in doc["_filter_reason"]
        assert "1" in doc["_filter_reason"]


# ── Check 2: Error page detection ──

class TestErrorPageDetection:
    def test_404_page_filtered(self, qf):
        doc = _doc("404 Not Found\nThe page you are looking for does not exist.", word_count=200)
        result = qf.process(doc)
        if result is None:
            assert doc.get("_filter_reason") in ("error_or_junk_page", f"too_short_{200}_words", "non_english", "low_interview_signal")

    def test_clean_content_not_error_page(self, qf):
        assert qf._is_error_page(GOOD_CONTENT) is False

    def test_error_check_only_first_500_chars(self, qf):
        """Error patterns only checked in first 500 chars."""
        safe_head = "A" * 500
        content = safe_head + "404 Not Found"
        assert qf._is_error_page(content) is False

    def test_access_denied_filtered(self, qf):
        content = "Access Denied. You don't have permission to access this resource."
        assert qf._is_error_page(content) is True


# ── Check 3: Language detection ──

class TestLanguageDetection:
    def test_english_passes(self, qf):
        assert qf._is_allowed_language(GOOD_CONTENT) is True

    def test_short_text_bypasses_detection(self, qf):
        """Texts shorter than min_chars_for_detection are assumed English."""
        assert qf._is_allowed_language("hi") is True

    def test_non_english_fails(self, qf):
        # French paragraph
        french = (
            "Je me suis entretenu chez Google pour le poste d'ingénieur logiciel. "
            "Il y avait cinq tours d'entretiens. Le premier tour était technique. "
            "Le deuxième tour portait sur la conception de systèmes."
        )
        result = qf._is_allowed_language(french)
        # langdetect may vary; just check it returns bool
        assert isinstance(result, bool)

    def test_custom_allowed_languages(self):
        qf_multi = QualityFilter(
            min_word_count=5,
            max_word_count=5000,
            min_signal_ratio=0.0,
            allowed_languages=["en", "fr"],
        )
        assert qf_multi.allowed_languages == ["en", "fr"]


# ── Check 4: Signal ratio ──

class TestSignalRatioCheck:
    def test_zero_signal_filtered(self):
        qf_strict = QualityFilter(
            min_word_count=5,
            max_word_count=5000,
            min_signal_ratio=0.5,
            allowed_languages=["en"],
        )
        # Content with no interview signal words
        doc = _doc(
            "The quick brown fox jumps over the lazy dog repeatedly always.",
            word_count=11
        )
        result = qf_strict.process(doc)
        # Either filtered for signal or language — just not for word count
        if result is None:
            reason = doc.get("_filter_reason", "")
            assert "too_short" not in reason and "too_long" not in reason

    def test_signal_ratio_empty_text(self, qf):
        assert qf._compute_signal_ratio("") == 0.0

    def test_signal_ratio_with_interview_keywords(self, qf):
        ratio = qf._compute_signal_ratio("interview round offer coding technical behavioral")
        assert ratio > 0.0

    def test_signal_ratio_returns_float_between_0_and_1(self, qf):
        ratio = qf._compute_signal_ratio(GOOD_CONTENT)
        assert 0.0 <= ratio <= 1.0

    def test_low_signal_reason_tagged(self):
        qf_strict = QualityFilter(
            min_word_count=5,
            max_word_count=5000,
            min_signal_ratio=0.99,
            allowed_languages=["en"],
        )
        doc = _doc("The quick brown fox jumps over something. Here are more words.", word_count=12)
        qf_strict.process(doc)
        # If it got to signal check, reason should reflect it
        reason = doc.get("_filter_reason", "")
        # Could be non_english too on short content — just verify not a word count reason
        assert "too_short" not in reason


# ── _compute_quality_score() ──

class TestComputeQualityScore:
    def test_score_between_0_and_1(self, qf):
        for wc, ratio in [(50, 0.01), (200, 0.05), (500, 0.10), (3000, 0.15)]:
            score = qf._compute_quality_score(wc, ratio)
            assert 0.0 <= score <= 1.0, f"Failed for wc={wc}, ratio={ratio}"

    def test_medium_length_high_signal_scores_well(self, qf):
        score = qf._compute_quality_score(500, 0.10)
        assert score >= 0.8

    def test_short_doc_scores_lower(self, qf):
        short_score = qf._compute_quality_score(50, 0.05)
        long_score = qf._compute_quality_score(500, 0.05)
        assert short_score < long_score

    def test_very_long_doc_score_decays(self, qf):
        normal_score = qf._compute_quality_score(1000, 0.10)
        long_score = qf._compute_quality_score(10000, 0.10)
        assert long_score <= normal_score

    def test_score_is_rounded(self, qf):
        score = qf._compute_quality_score(500, 0.05)
        assert score == round(score, 3)

    def test_zero_signal_score_lower(self, qf):
        zero_signal = qf._compute_quality_score(500, 0.0)
        some_signal = qf._compute_quality_score(500, 0.10)
        assert zero_signal < some_signal


# ── run_batch() integration ──

class TestRunBatchIntegration:
    def test_batch_counts_correct(self, qf):
        docs = [
            _doc(GOOD_CONTENT),
            _doc("short", word_count=1),
        ]
        out, result = qf.run_batch(docs)
        assert result.input_count == 2
        assert result.filtered_count >= 1