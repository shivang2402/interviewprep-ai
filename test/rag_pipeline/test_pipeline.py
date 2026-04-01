"""
Tests for src/rag_pipeline/pipeline.py

Covers:
- load_generation_config(): YAML loading from default and custom paths
- get_db_params(): extracting DB connection params from config
- build_generator(): full wiring of registry → retriever → generator
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path


# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

SAMPLE_CONFIG = {
    "gcp": {
        "project_id": "test-project",
        "region": "us-central1",
        "model_registry_name": "test-model",
    },
    "database": {
        "host": "localhost",
        "port": 5432,
        "dbname": "testdb",
        "user": "testuser",
        "password": "testpass",
    },
    "retrieval": {
        "top_k": 8,
        "fetch_multiplier": 2,
        "rrf_k": 60,
        "bm25_weight": 0.0,
        "vector_weight": 1.0,
    },
    "embedding_models": {
        "all-MiniLM-L6-v2": {"dim": 384, "column": "embeddings_all_minilm_l6_v2"},
    },
    "generation": {
        "openai_model": "gpt-4.1-mini",
        "temperature": 0.3,
        "max_tokens": 1024,
    },
}


# ─────────────────────────────────────────────────
# load_generation_config()
# ─────────────────────────────────────────────────

class TestLoadGenerationConfig:
    @patch("src.rag_pipeline.pipeline.yaml.safe_load")
    @patch("builtins.open", mock_open(read_data="key: value"))
    def test_loads_yaml_from_default_path(self, mock_yaml):
        from src.rag_pipeline.pipeline import load_generation_config

        mock_yaml.return_value = {"key": "value"}
        config = load_generation_config()

        assert config == {"key": "value"}

    @patch("src.rag_pipeline.pipeline.yaml.safe_load")
    @patch("builtins.open", mock_open(read_data="key: custom"))
    def test_loads_yaml_from_custom_path(self, mock_yaml):
        from src.rag_pipeline.pipeline import load_generation_config

        mock_yaml.return_value = {"key": "custom"}
        config = load_generation_config("/custom/path.yaml")

        assert config == {"key": "custom"}


# ─────────────────────────────────────────────────
# get_db_params()
# ─────────────────────────────────────────────────

class TestGetDbParams:
    def test_extracts_all_db_fields(self):
        from src.rag_pipeline.pipeline import get_db_params

        params = get_db_params(SAMPLE_CONFIG)

        assert params == {
            "host": "localhost",
            "port": 5432,
            "dbname": "testdb",
            "user": "testuser",
            "password": "testpass",
        }

    def test_missing_database_key_raises(self):
        from src.rag_pipeline.pipeline import get_db_params

        with pytest.raises(KeyError):
            get_db_params({})


# ─────────────────────────────────────────────────
# build_generator()
# ─────────────────────────────────────────────────

class TestBuildGenerator:
    @patch("src.rag_pipeline.pipeline.RAGGenerator")
    @patch("src.rag_pipeline.pipeline.HybridRetriever")
    @patch("src.rag_pipeline.pipeline.get_deployed_embedding_model")
    @patch("src.rag_pipeline.pipeline.load_generation_config")
    def test_wires_components_together(self, mock_load, mock_registry, mock_retriever_cls, mock_gen_cls):
        from src.rag_pipeline.pipeline import build_generator

        mock_load.return_value = SAMPLE_CONFIG
        mock_registry.return_value = {
            "model_name": "all-MiniLM-L6-v2",
            "embedding_dim": 384,
            "embedding_column": "embeddings_all_minilm_l6_v2",
        }
        mock_retriever = MagicMock()
        mock_retriever_cls.return_value = mock_retriever

        build_generator()

        mock_load.assert_called_once()
        mock_registry.assert_called_once_with(SAMPLE_CONFIG)
        mock_retriever_cls.assert_called_once()
        mock_gen_cls.assert_called_once_with(
            retriever=mock_retriever,
            generation_config=SAMPLE_CONFIG["generation"],
        )

    @patch("src.rag_pipeline.pipeline.RAGGenerator")
    @patch("src.rag_pipeline.pipeline.HybridRetriever")
    @patch("src.rag_pipeline.pipeline.get_deployed_embedding_model")
    @patch("src.rag_pipeline.pipeline.load_generation_config")
    def test_passes_db_params_to_retriever(self, mock_load, mock_registry, mock_retriever_cls, mock_gen_cls):
        from src.rag_pipeline.pipeline import build_generator

        mock_load.return_value = SAMPLE_CONFIG
        model_info = {
            "model_name": "all-MiniLM-L6-v2",
            "embedding_dim": 384,
            "embedding_column": "embeddings_all_minilm_l6_v2",
        }
        mock_registry.return_value = model_info

        build_generator()

        call_kwargs = mock_retriever_cls.call_args[1]
        assert call_kwargs["db_params"]["host"] == "localhost"
        assert call_kwargs["retrieval_config"] == SAMPLE_CONFIG["retrieval"]
        assert call_kwargs["model_info"] == model_info

    @patch("src.rag_pipeline.pipeline.RAGGenerator")
    @patch("src.rag_pipeline.pipeline.HybridRetriever")
    @patch("src.rag_pipeline.pipeline.get_deployed_embedding_model")
    @patch("src.rag_pipeline.pipeline.load_generation_config")
    def test_returns_rag_generator_instance(self, mock_load, mock_registry, mock_retriever_cls, mock_gen_cls):
        from src.rag_pipeline.pipeline import build_generator

        mock_load.return_value = SAMPLE_CONFIG
        mock_registry.return_value = {"model_name": "m", "embedding_dim": 384, "embedding_column": "col"}
        expected = MagicMock()
        mock_gen_cls.return_value = expected

        result = build_generator()

        assert result is expected

    @patch("src.rag_pipeline.pipeline.RAGGenerator")
    @patch("src.rag_pipeline.pipeline.HybridRetriever")
    @patch("src.rag_pipeline.pipeline.get_deployed_embedding_model")
    @patch("src.rag_pipeline.pipeline.load_generation_config")
    def test_custom_config_path_forwarded(self, mock_load, mock_registry, mock_retriever_cls, mock_gen_cls):
        from src.rag_pipeline.pipeline import build_generator

        mock_load.return_value = SAMPLE_CONFIG
        mock_registry.return_value = {"model_name": "m", "embedding_dim": 384, "embedding_column": "col"}

        build_generator("/my/config.yaml")

        mock_load.assert_called_once_with("/my/config.yaml")
