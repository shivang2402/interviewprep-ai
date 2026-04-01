"""
Tests for src/rag_pipeline/retriever.py

Covers:
- HybridRetriever.__init__(): wiring of config, model, and DB connection
- _vector_search(): SQL execution and result passthrough
- _bm25_search(): SQL execution and result passthrough
- _reciprocal_rank_fusion(): weighted RRF scoring and ranking
- retrieve(): full flow (encode → vector → bm25 → fuse → format)
- close(): connection cleanup
"""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, call


# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

RETRIEVAL_CONFIG = {
    "top_k": 3,
    "fetch_multiplier": 2,
    "rrf_k": 60,
    "vector_weight": 1.0,
    "bm25_weight": 0.5,
}

MODEL_INFO = {
    "model_name": "all-MiniLM-L6-v2",
    "embedding_dim": 384,
    "embedding_column": "embeddings_all_minilm_l6_v2",
}

DB_PARAMS = {
    "host": "localhost",
    "port": 5432,
    "dbname": "testdb",
    "user": "test",
    "password": "test",
}


def _make_row(chunk_id, text="some text", url="https://example.com", company="Google", role="SDE", score=0.9):
    return (chunk_id, text, url, company, role, score)


def _build_retriever(mock_pg, mock_st):
    """Construct a HybridRetriever with mocked DB and SentenceTransformer."""
    mock_conn = MagicMock()
    mock_pg.connect.return_value = mock_conn
    mock_model = MagicMock()
    mock_st.return_value = mock_model

    from src.rag_pipeline.retriever import HybridRetriever
    retriever = HybridRetriever(DB_PARAMS, RETRIEVAL_CONFIG, MODEL_INFO)
    return retriever, mock_conn, mock_model


# ─────────────────────────────────────────────────
# __init__()
# ─────────────────────────────────────────────────

class TestInit:
    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_stores_config(self, mock_pg, mock_st):
        retriever, _, _ = _build_retriever(mock_pg, mock_st)
        assert retriever.config == RETRIEVAL_CONFIG

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_stores_embedding_column(self, mock_pg, mock_st):
        retriever, _, _ = _build_retriever(mock_pg, mock_st)
        assert retriever.embedding_column == "embeddings_all_minilm_l6_v2"

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_connects_to_db(self, mock_pg, mock_st):
        _build_retriever(mock_pg, mock_st)
        mock_pg.connect.assert_called_once_with(**DB_PARAMS)

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_loads_sentence_transformer(self, mock_pg, mock_st):
        _build_retriever(mock_pg, mock_st)
        mock_st.assert_called_once_with("all-MiniLM-L6-v2")


# ─────────────────────────────────────────────────
# _vector_search()
# ─────────────────────────────────────────────────

class TestVectorSearch:
    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_executes_query_and_returns_results(self, mock_pg, mock_st):
        retriever, mock_conn, _ = _build_retriever(mock_pg, mock_st)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        expected = [_make_row("c1"), _make_row("c2")]
        mock_cursor.fetchall.return_value = expected
        mock_conn.cursor.return_value = mock_cursor

        embedding = np.array([0.1, 0.2, 0.3])
        results = retriever._vector_search(embedding, top_k=5)

        assert results == expected
        mock_cursor.execute.assert_called_once()

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_passes_embedding_as_list(self, mock_pg, mock_st):
        retriever, mock_conn, _ = _build_retriever(mock_pg, mock_st)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor

        embedding = np.array([0.1, 0.2])
        retriever._vector_search(embedding, top_k=3)

        args = mock_cursor.execute.call_args[0][1]
        assert args[0] == [0.1, 0.2]  # converted to list
        assert args[2] == 3           # top_k

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_query_references_embedding_column(self, mock_pg, mock_st):
        retriever, mock_conn, _ = _build_retriever(mock_pg, mock_st)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor

        retriever._vector_search(np.array([0.1]), top_k=1)

        sql = mock_cursor.execute.call_args[0][0]
        assert "embeddings_all_minilm_l6_v2" in sql


# ─────────────────────────────────────────────────
# _bm25_search()
# ─────────────────────────────────────────────────

class TestBM25Search:
    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_executes_query_and_returns_results(self, mock_pg, mock_st):
        retriever, mock_conn, _ = _build_retriever(mock_pg, mock_st)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        expected = [_make_row("c1", score=0.8)]
        mock_cursor.fetchall.return_value = expected
        mock_conn.cursor.return_value = mock_cursor

        results = retriever._bm25_search("system design interview", top_k=5)

        assert results == expected
        mock_cursor.execute.assert_called_once()

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_passes_query_text_and_top_k(self, mock_pg, mock_st):
        retriever, mock_conn, _ = _build_retriever(mock_pg, mock_st)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor

        retriever._bm25_search("coding interview", top_k=10)

        args = mock_cursor.execute.call_args[0][1]
        assert args[0] == "coding interview"
        assert args[1] == "coding interview"
        assert args[2] == 10

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_query_uses_tsquery(self, mock_pg, mock_st):
        retriever, mock_conn, _ = _build_retriever(mock_pg, mock_st)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor

        retriever._bm25_search("query", top_k=1)

        sql = mock_cursor.execute.call_args[0][0]
        assert "plainto_tsquery" in sql
        assert "ts_rank_cd" in sql


# ─────────────────────────────────────────────────
# _reciprocal_rank_fusion()
# ─────────────────────────────────────────────────

class TestReciprocalRankFusion:
    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_vector_only_results(self, mock_pg, mock_st):
        retriever, _, _ = _build_retriever(mock_pg, mock_st)
        vec = [_make_row("c1"), _make_row("c2")]
        bm25 = []

        fused = retriever._reciprocal_rank_fusion(vec, bm25, top_k=2)
        assert len(fused) == 2
        assert fused[0][0] == "c1"  # rank 1 has higher RRF score

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_bm25_only_results(self, mock_pg, mock_st):
        retriever, _, _ = _build_retriever(mock_pg, mock_st)
        vec = []
        bm25 = [_make_row("c1"), _make_row("c2")]

        fused = retriever._reciprocal_rank_fusion(vec, bm25, top_k=2)
        assert len(fused) == 2

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_overlapping_results_boosted(self, mock_pg, mock_st):
        retriever, _, _ = _build_retriever(mock_pg, mock_st)
        # c1 appears in both → should get boosted
        vec = [_make_row("c1"), _make_row("c2")]
        bm25 = [_make_row("c1"), _make_row("c3")]

        fused = retriever._reciprocal_rank_fusion(vec, bm25, top_k=3)
        fused_ids = [row[0] for row in fused]
        assert fused_ids[0] == "c1"  # c1 should rank first (boosted by both)

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_top_k_limits_output(self, mock_pg, mock_st):
        retriever, _, _ = _build_retriever(mock_pg, mock_st)
        vec = [_make_row(f"c{i}") for i in range(10)]
        bm25 = []

        fused = retriever._reciprocal_rank_fusion(vec, bm25, top_k=3)
        assert len(fused) == 3

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_empty_inputs_returns_empty(self, mock_pg, mock_st):
        retriever, _, _ = _build_retriever(mock_pg, mock_st)
        fused = retriever._reciprocal_rank_fusion([], [], top_k=5)
        assert fused == []

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_rrf_uses_config_weights(self, mock_pg, mock_st):
        """With bm25_weight=0, only vector results contribute scores."""
        retriever, _, _ = _build_retriever(mock_pg, mock_st)
        retriever.config = {**RETRIEVAL_CONFIG, "bm25_weight": 0.0, "vector_weight": 1.0}

        vec = [_make_row("c1")]
        bm25 = [_make_row("c2")]

        fused = retriever._reciprocal_rank_fusion(vec, bm25, top_k=2)
        fused_ids = [row[0] for row in fused]
        # c1 (vector) should rank above c2 (bm25 with 0 weight)
        assert fused_ids[0] == "c1"


# ─────────────────────────────────────────────────
# retrieve()
# ─────────────────────────────────────────────────

class TestRetrieve:
    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_returns_list_of_dicts(self, mock_pg, mock_st):
        retriever, _, mock_model = _build_retriever(mock_pg, mock_st)
        mock_model.encode.return_value = np.array([0.1, 0.2])

        retriever._vector_search = MagicMock(return_value=[_make_row("c1")])
        retriever._bm25_search = MagicMock(return_value=[])

        results = retriever.retrieve("Google SDE interview")

        assert isinstance(results, list)
        assert results[0]["id"] == "c1"
        assert results[0]["text"] == "some text"
        assert results[0]["source_url"] == "https://example.com"
        assert results[0]["company"] == "Google"
        assert results[0]["role"] == "SDE"

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_uses_config_top_k_when_none(self, mock_pg, mock_st):
        retriever, _, mock_model = _build_retriever(mock_pg, mock_st)
        mock_model.encode.return_value = np.array([0.1])

        retriever._vector_search = MagicMock(return_value=[])
        retriever._bm25_search = MagicMock(return_value=[])

        retriever.retrieve("query")

        # fetch_k = top_k(3) * fetch_multiplier(2) = 6
        retriever._vector_search.assert_called_once()
        assert retriever._vector_search.call_args[0][1] == 6

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_custom_top_k_overrides_config(self, mock_pg, mock_st):
        retriever, _, mock_model = _build_retriever(mock_pg, mock_st)
        mock_model.encode.return_value = np.array([0.1])

        retriever._vector_search = MagicMock(return_value=[])
        retriever._bm25_search = MagicMock(return_value=[])

        retriever.retrieve("query", top_k=5)

        # fetch_k = 5 * 2 = 10
        assert retriever._vector_search.call_args[0][1] == 10

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_encodes_query_with_model(self, mock_pg, mock_st):
        retriever, _, mock_model = _build_retriever(mock_pg, mock_st)
        mock_model.encode.return_value = np.array([0.1])

        retriever._vector_search = MagicMock(return_value=[])
        retriever._bm25_search = MagicMock(return_value=[])

        retriever.retrieve("my query")

        mock_model.encode.assert_called_once_with("my query")

    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_empty_results_returns_empty_list(self, mock_pg, mock_st):
        retriever, _, mock_model = _build_retriever(mock_pg, mock_st)
        mock_model.encode.return_value = np.array([0.1])

        retriever._vector_search = MagicMock(return_value=[])
        retriever._bm25_search = MagicMock(return_value=[])

        results = retriever.retrieve("query")
        assert results == []


# ─────────────────────────────────────────────────
# close()
# ─────────────────────────────────────────────────

class TestClose:
    @patch("src.rag_pipeline.retriever.SentenceTransformer")
    @patch("src.rag_pipeline.retriever.psycopg2")
    def test_closes_db_connection(self, mock_pg, mock_st):
        retriever, mock_conn, _ = _build_retriever(mock_pg, mock_st)
        retriever.close()
        mock_conn.close.assert_called_once()
