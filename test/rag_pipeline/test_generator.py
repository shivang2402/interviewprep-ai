"""
Tests for src/rag_pipeline/generator.py

Covers:
- RAGGenerator.__init__(): wiring of retriever, config, and OpenAI client
- generate(): retrieval → prompt → OpenAI call → response formatting
- close(): delegates to retriever.close()
"""
import pytest
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

GENERATION_CONFIG = {
    "openai_model": "gpt-4.1-mini",
    "temperature": 0.3,
    "max_tokens": 1024,
}


def _make_chunk(**overrides):
    defaults = {
        "id": "c1",
        "text": "Google SDE interview had 5 rounds.",
        "source_url": "https://example.com/google",
        "company": "Google",
        "role": "SDE",
    }
    defaults.update(overrides)
    return defaults


def _mock_openai_response(content="Here is my answer.", prompt_tokens=100, completion_tokens=50):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = prompt_tokens + completion_tokens
    return response


# ─────────────────────────────────────────────────
# __init__()
# ─────────────────────────────────────────────────

class TestInit:
    @patch("src.rag_pipeline.generator.OpenAI")
    def test_stores_retriever_and_config(self, mock_openai_cls):
        from src.rag_pipeline.generator import RAGGenerator

        mock_retriever = MagicMock()
        gen = RAGGenerator(mock_retriever, GENERATION_CONFIG)

        assert gen.retriever is mock_retriever
        assert gen.config == GENERATION_CONFIG

    @patch("src.rag_pipeline.generator.OpenAI")
    def test_creates_openai_client(self, mock_openai_cls):
        from src.rag_pipeline.generator import RAGGenerator

        RAGGenerator(MagicMock(), GENERATION_CONFIG)
        mock_openai_cls.assert_called_once()


# ─────────────────────────────────────────────────
# generate()
# ─────────────────────────────────────────────────

class TestGenerate:
    @patch("src.rag_pipeline.generator.build_messages")
    @patch("src.rag_pipeline.generator.OpenAI")
    def test_calls_retriever_with_query(self, mock_openai_cls, mock_build):
        from src.rag_pipeline.generator import RAGGenerator

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [_make_chunk()]
        mock_build.return_value = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_openai_response()

        gen = RAGGenerator(mock_retriever, GENERATION_CONFIG)
        gen.generate("Google SDE interview")

        mock_retriever.retrieve.assert_called_once_with("Google SDE interview", top_k=None)

    @patch("src.rag_pipeline.generator.build_messages")
    @patch("src.rag_pipeline.generator.OpenAI")
    def test_passes_top_k_to_retriever(self, mock_openai_cls, mock_build):
        from src.rag_pipeline.generator import RAGGenerator

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [_make_chunk()]
        mock_build.return_value = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_openai_response()

        gen = RAGGenerator(mock_retriever, GENERATION_CONFIG)
        gen.generate("query", top_k=5)

        mock_retriever.retrieve.assert_called_once_with("query", top_k=5)

    @patch("src.rag_pipeline.generator.build_messages")
    @patch("src.rag_pipeline.generator.OpenAI")
    def test_calls_openai_with_config(self, mock_openai_cls, mock_build):
        from src.rag_pipeline.generator import RAGGenerator

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [_make_chunk()]
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
        mock_build.return_value = messages
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_openai_response()

        gen = RAGGenerator(mock_retriever, GENERATION_CONFIG)
        gen.generate("query")

        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
        )

    @patch("src.rag_pipeline.generator.build_messages")
    @patch("src.rag_pipeline.generator.OpenAI")
    def test_returns_correct_structure(self, mock_openai_cls, mock_build):
        from src.rag_pipeline.generator import RAGGenerator

        chunks = [_make_chunk()]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = chunks
        mock_build.return_value = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            content="The answer is 42.",
            prompt_tokens=200,
            completion_tokens=80,
        )

        gen = RAGGenerator(mock_retriever, GENERATION_CONFIG)
        result = gen.generate("what is life?")

        assert result["query"] == "what is life?"
        assert result["answer"] == "The answer is 42."
        assert result["chunks"] == chunks
        assert result["model"] == "gpt-4.1-mini"
        assert result["usage"]["prompt_tokens"] == 200
        assert result["usage"]["completion_tokens"] == 80
        assert result["usage"]["total_tokens"] == 280

    @patch("src.rag_pipeline.generator.build_messages")
    @patch("src.rag_pipeline.generator.OpenAI")
    def test_builds_messages_from_chunks(self, mock_openai_cls, mock_build):
        from src.rag_pipeline.generator import RAGGenerator

        chunks = [_make_chunk(id="c1"), _make_chunk(id="c2")]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = chunks
        mock_build.return_value = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_openai_response()

        gen = RAGGenerator(mock_retriever, GENERATION_CONFIG)
        gen.generate("query")

        mock_build.assert_called_once_with("query", chunks)

    @patch("src.rag_pipeline.generator.build_messages")
    @patch("src.rag_pipeline.generator.OpenAI")
    def test_no_chunks_still_calls_openai(self, mock_openai_cls, mock_build):
        from src.rag_pipeline.generator import RAGGenerator

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_build.return_value = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            content="I don't have enough context."
        )

        gen = RAGGenerator(mock_retriever, GENERATION_CONFIG)
        result = gen.generate("query about nothing")

        assert result["chunks"] == []
        assert "don't have enough context" in result["answer"]


# ─────────────────────────────────────────────────
# close()
# ─────────────────────────────────────────────────

class TestClose:
    @patch("src.rag_pipeline.generator.OpenAI")
    def test_close_delegates_to_retriever(self, mock_openai_cls):
        from src.rag_pipeline.generator import RAGGenerator

        mock_retriever = MagicMock()
        gen = RAGGenerator(mock_retriever, GENERATION_CONFIG)
        gen.close()

        mock_retriever.close.assert_called_once()
