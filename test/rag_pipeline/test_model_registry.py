"""
Tests for src/rag_pipeline/model_registry.py

Covers:
- _get_config_from_registry(): Vertex AI model lookup and label extraction
- _get_model_name_from_mlflow(): MLflow parent/child run traversal
- get_deployed_embedding_model(): full flow → model info dict
"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

SAMPLE_CONFIG = {
    "gcp": {
        "project_id": "test-project",
        "region": "us-central1",
        "model_registry_name": "test-model",
    },
    "mlflow": {
        "tracking_uri": "http://localhost:5000",
        "experiment_name": "test-experiment",
    },
    "embedding_models": {
        "all-MiniLM-L6-v2": {"dim": 384, "column": "embeddings_all_minilm_l6_v2"},
        "all-mpnet-base-v2": {"dim": 768, "column": "embeddings_all_mpnet_base_v2"},
    },
}


# ─────────────────────────────────────────────────
# _get_config_from_registry()
# ─────────────────────────────────────────────────

class TestGetConfigFromRegistry:
    @patch("src.rag_pipeline.model_registry.aiplatform")
    def test_returns_best_config_label(self, mock_aip):
        from src.rag_pipeline.model_registry import _get_config_from_registry

        mock_model = MagicMock()
        mock_model.labels = {"best-config": "all-minilm-l6-v2_dim384_vector"}
        mock_model.version_id = "1"
        mock_aip.Model.list.return_value = [mock_model]

        result = _get_config_from_registry(SAMPLE_CONFIG)
        assert result == "all-minilm-l6-v2_dim384_vector"

    @patch("src.rag_pipeline.model_registry.aiplatform")
    def test_inits_aiplatform_with_gcp_config(self, mock_aip):
        from src.rag_pipeline.model_registry import _get_config_from_registry

        mock_model = MagicMock()
        mock_model.labels = {"best-config": "label"}
        mock_model.version_id = "1"
        mock_aip.Model.list.return_value = [mock_model]

        _get_config_from_registry(SAMPLE_CONFIG)

        mock_aip.init.assert_called_once_with(
            project="test-project", location="us-central1"
        )

    @patch("src.rag_pipeline.model_registry.aiplatform")
    def test_no_models_raises(self, mock_aip):
        from src.rag_pipeline.model_registry import _get_config_from_registry

        mock_aip.Model.list.return_value = []

        with pytest.raises(RuntimeError, match="No model found"):
            _get_config_from_registry(SAMPLE_CONFIG)

    @patch("src.rag_pipeline.model_registry.aiplatform")
    def test_no_best_config_label_raises(self, mock_aip):
        from src.rag_pipeline.model_registry import _get_config_from_registry

        mock_model = MagicMock()
        mock_model.labels = {"other-label": "value"}
        mock_model.version_id = "1"
        mock_aip.Model.list.return_value = [mock_model]

        with pytest.raises(RuntimeError, match="no 'best-config' label"):
            _get_config_from_registry(SAMPLE_CONFIG)

    @patch("src.rag_pipeline.model_registry.aiplatform")
    def test_none_labels_raises(self, mock_aip):
        from src.rag_pipeline.model_registry import _get_config_from_registry

        mock_model = MagicMock()
        mock_model.labels = None
        mock_model.version_id = "1"
        mock_aip.Model.list.return_value = [mock_model]

        with pytest.raises(RuntimeError, match="no 'best-config' label"):
            _get_config_from_registry(SAMPLE_CONFIG)


# ─────────────────────────────────────────────────
# _get_model_name_from_mlflow()
# ─────────────────────────────────────────────────

class TestGetModelNameFromMlflow:
    @patch("src.rag_pipeline.model_registry.mlflow")
    def test_returns_model_name(self, mock_mlflow):
        from src.rag_pipeline.model_registry import _get_model_name_from_mlflow

        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "exp_1"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment

        parent_df = pd.DataFrame([{
            "run_id": "parent_run_123",
            "tags.best_config": "best_config_name",
        }])
        child_df = pd.DataFrame([{
            "run_id": "child_run_456",
            "params.model_name": "sentence-transformers/all-MiniLM-L6-v2",
        }])
        mock_mlflow.search_runs.side_effect = [parent_df, child_df]

        result = _get_model_name_from_mlflow(SAMPLE_CONFIG, "label")
        assert result == "sentence-transformers/all-MiniLM-L6-v2"

    @patch("src.rag_pipeline.model_registry.mlflow")
    def test_no_experiment_raises(self, mock_mlflow):
        from src.rag_pipeline.model_registry import _get_model_name_from_mlflow

        mock_mlflow.get_experiment_by_name.return_value = None

        with pytest.raises(RuntimeError, match="not found"):
            _get_model_name_from_mlflow(SAMPLE_CONFIG, "label")

    @patch("src.rag_pipeline.model_registry.mlflow")
    def test_no_parent_runs_raises(self, mock_mlflow):
        from src.rag_pipeline.model_registry import _get_model_name_from_mlflow

        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "exp_1"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment
        mock_mlflow.search_runs.return_value = pd.DataFrame()

        with pytest.raises(RuntimeError, match="No pipeline parent runs"):
            _get_model_name_from_mlflow(SAMPLE_CONFIG, "label")

    @patch("src.rag_pipeline.model_registry.mlflow")
    def test_no_best_config_tag_raises(self, mock_mlflow):
        from src.rag_pipeline.model_registry import _get_model_name_from_mlflow

        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "exp_1"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment

        parent_df = pd.DataFrame([{
            "run_id": "parent_run_123",
        }])
        mock_mlflow.search_runs.return_value = parent_df

        with pytest.raises(RuntimeError, match="no 'best_config'"):
            _get_model_name_from_mlflow(SAMPLE_CONFIG, "label")

    @patch("src.rag_pipeline.model_registry.mlflow")
    def test_no_child_run_found_falls_back_then_raises(self, mock_mlflow):
        from src.rag_pipeline.model_registry import _get_model_name_from_mlflow

        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "exp_1"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment

        parent_df = pd.DataFrame([{
            "run_id": "parent_run_123",
            "tags.best_config": "missing_config",
        }])
        empty_df = pd.DataFrame()
        mock_mlflow.search_runs.side_effect = [parent_df, empty_df, empty_df]

        with pytest.raises(RuntimeError, match="No MLflow run found"):
            _get_model_name_from_mlflow(SAMPLE_CONFIG, "label")

    @patch("src.rag_pipeline.model_registry.mlflow")
    def test_child_run_missing_model_name_raises(self, mock_mlflow):
        from src.rag_pipeline.model_registry import _get_model_name_from_mlflow

        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "exp_1"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment

        parent_df = pd.DataFrame([{
            "run_id": "parent_run_123",
            "tags.best_config": "some_config",
        }])
        child_df = pd.DataFrame([{
            "run_id": "child_run_456",
        }])
        mock_mlflow.search_runs.side_effect = [parent_df, child_df]

        with pytest.raises(RuntimeError, match="no 'model_name' param"):
            _get_model_name_from_mlflow(SAMPLE_CONFIG, "label")

    @patch.dict("os.environ", {"MLFLOW_TRACKING_URI": "http://env-override:5000"})
    @patch("src.rag_pipeline.model_registry.mlflow")
    def test_uses_env_var_tracking_uri(self, mock_mlflow):
        from src.rag_pipeline.model_registry import _get_model_name_from_mlflow

        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "exp_1"
        mock_mlflow.get_experiment_by_name.return_value = mock_experiment

        parent_df = pd.DataFrame([{
            "run_id": "parent_123",
            "tags.best_config": "cfg",
        }])
        child_df = pd.DataFrame([{
            "run_id": "child_456",
            "params.model_name": "all-MiniLM-L6-v2",
        }])
        mock_mlflow.search_runs.side_effect = [parent_df, child_df]

        _get_model_name_from_mlflow(SAMPLE_CONFIG, "label")

        mock_mlflow.set_tracking_uri.assert_called_once_with("http://env-override:5000")


# ─────────────────────────────────────────────────
# get_deployed_embedding_model()
# ─────────────────────────────────────────────────

class TestGetDeployedEmbeddingModel:
    @patch("src.rag_pipeline.model_registry._get_model_name_from_mlflow")
    @patch("src.rag_pipeline.model_registry._get_config_from_registry")
    def test_returns_model_info_dict(self, mock_registry, mock_mlflow):
        from src.rag_pipeline.model_registry import get_deployed_embedding_model

        mock_registry.return_value = "all-minilm-label"
        mock_mlflow.return_value = "all-MiniLM-L6-v2"

        result = get_deployed_embedding_model(SAMPLE_CONFIG)

        assert result == {
            "model_name": "all-MiniLM-L6-v2",
            "embedding_dim": 384,
            "embedding_column": "embeddings_all_minilm_l6_v2",
        }

    @patch("src.rag_pipeline.model_registry._get_model_name_from_mlflow")
    @patch("src.rag_pipeline.model_registry._get_config_from_registry")
    def test_strips_sentence_transformers_prefix(self, mock_registry, mock_mlflow):
        from src.rag_pipeline.model_registry import get_deployed_embedding_model

        mock_registry.return_value = "label"
        mock_mlflow.return_value = "sentence-transformers/all-mpnet-base-v2"

        result = get_deployed_embedding_model(SAMPLE_CONFIG)

        assert result["model_name"] == "all-mpnet-base-v2"
        assert result["embedding_dim"] == 768

    @patch("src.rag_pipeline.model_registry._get_model_name_from_mlflow")
    @patch("src.rag_pipeline.model_registry._get_config_from_registry")
    def test_unknown_model_raises_value_error(self, mock_registry, mock_mlflow):
        from src.rag_pipeline.model_registry import get_deployed_embedding_model

        mock_registry.return_value = "label"
        mock_mlflow.return_value = "unknown-model-xyz"

        with pytest.raises(ValueError, match="not in embedding_models config"):
            get_deployed_embedding_model(SAMPLE_CONFIG)

    @patch("src.rag_pipeline.model_registry._get_model_name_from_mlflow")
    @patch("src.rag_pipeline.model_registry._get_config_from_registry")
    def test_calls_registry_then_mlflow(self, mock_registry, mock_mlflow):
        from src.rag_pipeline.model_registry import get_deployed_embedding_model

        mock_registry.return_value = "config_label"
        mock_mlflow.return_value = "all-MiniLM-L6-v2"

        get_deployed_embedding_model(SAMPLE_CONFIG)

        mock_registry.assert_called_once_with(SAMPLE_CONFIG)
        mock_mlflow.assert_called_once_with(SAMPLE_CONFIG, "config_label")
