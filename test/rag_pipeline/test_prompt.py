"""
Tests for src/rag_pipeline/prompt.py

Covers:
- build_context(): chunk formatting with indices and source URLs
- build_messages(): system/user message structure and content assembly
"""
import pytest

from src.rag_pipeline.prompt import build_context, build_messages, SYSTEM_PROMPT


# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

def _make_chunk(**overrides):
    defaults = {
        "id": "chunk_1",
        "text": "We had two rounds of interviews at Google.",
        "source_url": "https://example.com/google-sde",
        "company": "Google",
        "role": "SDE",
    }
    defaults.update(overrides)
    return defaults


# ─────────────────────────────────────────────────
# build_context()
# ─────────────────────────────────────────────────

class TestBuildContext:
    def test_single_chunk_format(self):
        chunks = [_make_chunk()]
        ctx = build_context(chunks)
        assert "--- Chunk 1 ---" in ctx
        assert "https://example.com/google-sde" in ctx
        assert "two rounds of interviews" in ctx

    def test_multiple_chunks_numbered_sequentially(self):
        chunks = [
            _make_chunk(id="c1", text="First chunk text"),
            _make_chunk(id="c2", text="Second chunk text"),
            _make_chunk(id="c3", text="Third chunk text"),
        ]
        ctx = build_context(chunks)
        assert "--- Chunk 1 ---" in ctx
        assert "--- Chunk 2 ---" in ctx
        assert "--- Chunk 3 ---" in ctx
        assert ctx.index("Chunk 1") < ctx.index("Chunk 2") < ctx.index("Chunk 3")

    def test_empty_chunks_returns_empty_string(self):
        ctx = build_context([])
        assert ctx == ""

    def test_source_url_included_per_chunk(self):
        chunks = [
            _make_chunk(source_url="https://a.com"),
            _make_chunk(source_url="https://b.com"),
        ]
        ctx = build_context(chunks)
        assert "https://a.com" in ctx
        assert "https://b.com" in ctx

    def test_chunk_text_preserved_verbatim(self):
        raw = "Round 1: System Design. Round 2: Behavioral."
        chunks = [_make_chunk(text=raw)]
        ctx = build_context(chunks)
        assert raw in ctx


# ─────────────────────────────────────────────────
# build_messages()
# ─────────────────────────────────────────────────

class TestBuildMessages:
    def test_returns_two_messages(self):
        chunks = [_make_chunk()]
        messages = build_messages("Tell me about Google SDE", chunks)
        assert len(messages) == 2

    def test_first_message_is_system(self):
        messages = build_messages("query", [_make_chunk()])
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT

    def test_second_message_is_user(self):
        messages = build_messages("query", [_make_chunk()])
        assert messages[1]["role"] == "user"

    def test_user_message_contains_query(self):
        query = "How is the Amazon SDE interview?"
        messages = build_messages(query, [_make_chunk()])
        assert query in messages[1]["content"]

    def test_user_message_contains_context(self):
        chunks = [_make_chunk(text="Amazon has 4 rounds")]
        messages = build_messages("query", chunks)
        assert "Amazon has 4 rounds" in messages[1]["content"]

    def test_user_message_contains_context_header(self):
        messages = build_messages("query", [_make_chunk()])
        assert "Context from real interview experiences" in messages[1]["content"]

    def test_empty_chunks_still_produces_valid_messages(self):
        messages = build_messages("query", [])
        assert len(messages) == 2
        assert "User Question: query" in messages[1]["content"]
