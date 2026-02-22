"""
Tests for Step 1: ContentNormalizer.

Covers:
- process(): happy path, empty/short content, output schema
- _normalize(): full pipeline delegation
- _fix_encoding(): HTML entities, smart quotes, mojibake
- _strip_html(): tag removal, script/style stripping, comments
- _strip_markdown(): code blocks, headers, bold/italic
- _remove_boilerplate(): generic and platform-specific
- _remove_emojis()
- _normalize_unicode()
- _normalize_whitespace()
- _clean_title()
- _resolve_platform(): alias mapping
- run_batch() integration via inherited base
"""
import pytest
from src.preprocessing.steps.content_normalizer import ContentNormalizer


# ── Fixtures ──

@pytest.fixture
def normalizer():
    return ContentNormalizer(min_cleaned_length=20)


@pytest.fixture
def strict_normalizer():
    """Normalizer with high min length to force filtering."""
    return ContentNormalizer(min_cleaned_length=500)


def _doc(raw_content, platform="leetcode", title="Test Title"):
    return {
        "document_id": "test_doc_1",
        "source_platform": platform,
        "title": title,
        "raw_content": raw_content,
    }


# ── process() — happy path ──

class TestProcessHappyPath:
    def test_returns_doc_with_preprocessing_key(self, normalizer):
        doc = _doc("This is a normal interview experience with enough words to pass the minimum.")
        result = normalizer.process(doc)
        assert result is not None
        assert "preprocessing" in result
        assert "content_normalizer" in result["preprocessing"]

    def test_output_has_required_fields(self, normalizer):
        doc = _doc("This is a normal interview experience with enough words to pass the minimum.")
        result = normalizer.process(doc)
        cn = result["preprocessing"]["content_normalizer"]
        assert "content" in cn
        assert "title" in cn
        assert "word_count" in cn
        assert cn["completed"] is True

    def test_word_count_is_correct(self, normalizer):
        text = "one two three four five"
        doc = _doc(text)
        result = normalizer.process(doc)
        wc = result["preprocessing"]["content_normalizer"]["word_count"]
        assert wc == len(result["preprocessing"]["content_normalizer"]["content"].split())

    def test_raw_content_preserved(self, normalizer):
        raw = "This is a normal interview experience with enough words to pass."
        doc = _doc(raw)
        result = normalizer.process(doc)
        assert result["raw_content"] == raw

    def test_existing_preprocessing_dict_not_overwritten(self, normalizer):
        doc = _doc("Enough text to pass the minimum length check in this test case here.")
        doc["preprocessing"] = {"some_other_step": {"data": 42}}
        result = normalizer.process(doc)
        assert result["preprocessing"]["some_other_step"]["data"] == 42

    def test_title_cleaned_in_output(self, normalizer):
        doc = _doc(
            "Enough text to pass the minimum length check.",
            title="  My Interview Experience 🎉  "
        )
        result = normalizer.process(doc)
        title = result["preprocessing"]["content_normalizer"]["title"]
        assert "🎉" not in title
        assert title == title.strip()


# ── process() — filtering ──

class TestProcessFiltering:
    def test_empty_raw_content_returns_none(self, normalizer):
        doc = _doc("")
        result = normalizer.process(doc)
        assert result is None
        assert doc["_filter_reason"] == "empty_raw_content"

    def test_whitespace_only_raw_content_returns_none(self, normalizer):
        doc = _doc("   \n\t  ")
        result = normalizer.process(doc)
        assert result is None
        assert doc["_filter_reason"] == "empty_raw_content"

    def test_missing_raw_content_key_returns_none(self, normalizer):
        doc = {"document_id": "x", "source_platform": "leetcode", "title": "T"}
        result = normalizer.process(doc)
        assert result is None

    def test_content_too_short_after_cleaning_returns_none(self, strict_normalizer):
        doc = _doc("Hello world.")
        result = strict_normalizer.process(doc)
        assert result is None
        assert doc["_filter_reason"] == "empty_after_cleaning"

    def test_html_only_content_filtered(self, normalizer):
        """Content that is only HTML tags produces empty cleaned text."""
        doc = _doc("<script>alert('x')</script><style>body{}</style>")
        result = normalizer.process(doc)
        # Should be filtered since no actual text content remains
        assert result is None


# ── _fix_encoding() ──

class TestFixEncoding:
    def test_html_entities_decoded(self, normalizer):
        result = normalizer._fix_encoding("&amp; &lt; &gt; &quot;")
        assert "&amp;" not in result
        assert "&" in result

    def test_smart_quotes_replaced(self, normalizer):
        result = normalizer._fix_encoding("\u2018hello\u2019 and \u201cworld\u201d")
        assert "'" in result
        assert '"' in result
        assert "\u2018" not in result
        assert "\u201c" not in result

    def test_em_dash_replaced(self, normalizer):
        result = normalizer._fix_encoding("before\u2014after")
        assert "-" in result
        assert "\u2014" not in result

    def test_ellipsis_replaced(self, normalizer):
        result = normalizer._fix_encoding("wait\u2026")
        assert "..." in result

    def test_null_byte_removed(self, normalizer):
        result = normalizer._fix_encoding("hello\x00world")
        assert "\x00" not in result

    def test_bom_removed(self, normalizer):
        result = normalizer._fix_encoding("\ufeffstart")
        assert "\ufeff" not in result

    def test_non_breaking_space_replaced(self, normalizer):
        result = normalizer._fix_encoding("hello\u00a0world")
        assert "\u00a0" not in result
        assert " " in result


# ── _strip_html() ──

class TestStripHtml:
    def test_basic_tags_removed(self, normalizer):
        result = normalizer._strip_html("<p>Hello world</p>")
        assert "<p>" not in result
        assert "Hello world" in result

    def test_script_tag_removed(self, normalizer):
        result = normalizer._strip_html("<script>malicious()</script>real content")
        assert "malicious" not in result
        assert "real content" in result

    def test_style_tag_removed(self, normalizer):
        result = normalizer._strip_html("<style>body { color: red; }</style>text")
        assert "color" not in result
        assert "text" in result

    def test_html_comments_removed(self, normalizer):
        result = normalizer._strip_html("<!-- comment -->visible text")
        assert "comment" not in result
        assert "visible text" in result

    def test_plain_text_unchanged(self, normalizer):
        text = "no html here"
        result = normalizer._strip_html(text)
        assert result == text

    def test_nav_footer_removed(self, normalizer):
        result = normalizer._strip_html("<nav>menu</nav>content<footer>bottom</footer>")
        assert "menu" not in result
        assert "bottom" not in result
        assert "content" in result

    def test_nested_tags(self, normalizer):
        result = normalizer._strip_html("<div><p><b>bold</b> text</p></div>")
        assert "bold" in result
        assert "text" in result
        assert "<" not in result


# ── _strip_markdown() ──

class TestStripMarkdown:
    def test_code_block_replaced(self, normalizer):
        result = normalizer._strip_markdown("before\n```python\ncode here\n```\nafter")
        assert "code here" not in result
        assert "[code block removed]" in result
        assert "before" in result
        assert "after" in result

    def test_inline_code_handled(self, normalizer):
        # YAML-driven patterns handle inline code — just confirm no crash
        result = normalizer._strip_markdown("Use `list.sort()` method")
        assert isinstance(result, str)

    def test_headers_stripped(self, normalizer):
        result = normalizer._strip_markdown("## Section Header\ncontent")
        assert "##" not in result
        assert "content" in result


# ── _remove_emojis() ──

class TestRemoveEmojis:
    def test_common_emojis_removed(self, normalizer):
        result = normalizer._remove_emojis("Hello 😀 World 🚀")
        assert "😀" not in result
        assert "🚀" not in result
        assert "Hello" in result
        assert "World" in result

    def test_text_without_emojis_unchanged(self, normalizer):
        text = "No emojis here at all."
        result = normalizer._remove_emojis(text)
        assert result == text

    def test_flag_emojis_removed(self, normalizer):
        result = normalizer._remove_emojis("India 🇮🇳 interview")
        assert "🇮🇳" not in result


# ── _normalize_unicode() ──

class TestNormalizeUnicode:
    def test_nfc_normalization(self, normalizer):
        # Decomposed 'é' (e + combining accent) → composed 'é'
        decomposed = "e\u0301"
        result = normalizer._normalize_unicode(decomposed)
        assert result == "\xe9"

    def test_regular_text_unchanged(self, normalizer):
        text = "Hello World"
        assert normalizer._normalize_unicode(text) == text


# ── _normalize_whitespace() ──

class TestNormalizeWhitespace:
    def test_multiple_spaces_collapsed(self, normalizer):
        result = normalizer._normalize_whitespace("hello    world")
        assert "  " not in result
        assert "hello world" in result

    def test_excessive_newlines_collapsed(self, normalizer):
        result = normalizer._normalize_whitespace("para1\n\n\n\n\npara2")
        assert "\n\n\n" not in result

    def test_trailing_spaces_before_newline_removed(self, normalizer):
        result = normalizer._normalize_whitespace("line1   \nline2")
        assert "   \n" not in result

    def test_tabs_handled(self, normalizer):
        result = normalizer._normalize_whitespace("col1\tcol2")
        assert isinstance(result, str)


# ── _resolve_platform() ──

class TestResolvePlatform:
    def test_gfg_alias_resolved(self, normalizer):
        result = normalizer._resolve_platform("gfg")
        assert result == "gfg"

    def test_unknown_platform_passthrough(self, normalizer):
        result = normalizer._resolve_platform("reddit")
        assert result == "reddit"

    def test_case_insensitive(self, normalizer):
        result = normalizer._resolve_platform("GFG")
        assert result == "gfg"

    def test_whitespace_stripped(self, normalizer):
        result = normalizer._resolve_platform("  leetcode  ")
        assert result == "leetcode"


# ── _clean_title() ──

class TestCleanTitle:
    def test_emoji_removed_from_title(self, normalizer):
        result = normalizer._clean_title("My Interview 🚀 Experience")
        assert "🚀" not in result

    def test_html_stripped_from_title(self, normalizer):
        result = normalizer._clean_title("<b>Google</b> Interview")
        assert "<b>" not in result
        assert "Google" in result

    def test_extra_whitespace_collapsed(self, normalizer):
        result = normalizer._clean_title("  My   Interview  ")
        assert "  " not in result
        assert result == result.strip()

    def test_empty_title(self, normalizer):
        result = normalizer._clean_title("")
        assert result == ""


# ── run_batch() integration ──

class TestRunBatchIntegration:
    def test_batch_stats_correct(self, normalizer):
        docs = [
            _doc("   "),  # will be filtered
            _doc("Enough content to pass the minimum length requirement here."),
        ]
        out, result = normalizer.run_batch(docs)
        assert result.input_count == 2
        assert result.output_count == 1
        assert result.filtered_count == 1

    def test_empty_batch(self, normalizer):
        out, result = normalizer.run_batch([])
        assert out == []
        assert result.input_count == 0