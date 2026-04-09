"""
Fetches the best deployed embedding model config.

Flow:
  1. Vertex AI Model Registry → get latest model → read 'best-config' label
     (sanitized, e.g. "sentence-transformers-all-minilm-l6-v2_dim384_vector")
  2. MLflow → find latest pipeline parent run → read 'best_config'
     tag/metric → find child run → extract 'model_name' param
  3. (Fallback) Resolve model name directly from the label string
  4. Map to embedding dim + DB column via generation_config.yaml
"""

import os
import mlflow
from google.cloud import aiplatform


def _get_config_from_registry(config: dict) -> str:
    """
    Step 1: Query Vertex AI Model Registry for the latest model,
    return the 'best-config' label value (sanitized by GCP).
    """
    gcp = config["gcp"]
    registry_name = gcp["model_registry_name"]

    aiplatform.init(project=gcp["project_id"], location=gcp["region"])

    models = aiplatform.Model.list(
        filter=f'display_name="{registry_name}"',
        order_by="update_time desc",
    )

    if not models:
        raise RuntimeError(
            f"No model found in Vertex AI registry with name '{registry_name}'."
        )

    latest = models[0]
    labels = latest.labels or {}
    config_label = labels.get("best-config")

    if not config_label:
        raise RuntimeError(
            f"Model '{registry_name}' (version: {latest.version_id}) "
            f"has no 'best-config' label. Labels found: {labels}"
        )

    print(
        f"Vertex AI registry: {registry_name} "
        f"(version: {latest.version_id}) → best-config='{config_label}'"
    )
    return config_label


def _get_model_name_from_mlflow(config: dict, config_label: str) -> str:
    """
    Step 2: Find the latest pipeline parent run in MLflow.
    Step 3: Read best_config from parent → find child run → extract model_name.
    """
    mlflow_cfg = config.get("mlflow", {})
    mlflow_uri = os.environ.get(
        "MLFLOW_TRACKING_URI", mlflow_cfg.get("tracking_uri")
    )
    if not mlflow_uri:
        raise RuntimeError(
            "MLFLOW_TRACKING_URI env var or mlflow.tracking_uri config required."
        )

    mlflow.set_tracking_uri(mlflow_uri)

    experiment_name = mlflow_cfg.get(
        "experiment_name", "interviewprep-retrieval-eval"
    )
    experiment = mlflow.get_experiment_by_name(experiment_name)

    if experiment is None:
        raise RuntimeError(
            f"MLflow experiment '{experiment_name}' not found."
        )

    exp_id = experiment.experiment_id

    # Step 2: Find latest pipeline parent run
    parent_runs = mlflow.search_runs(
        experiment_ids=[exp_id],
        filter_string="tags.run_type = 'pipeline_parent'",
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )

    if parent_runs.empty:
        raise RuntimeError(
            f"No pipeline parent runs found in experiment '{experiment_name}'."
        )

    parent = parent_runs.iloc[0]
    parent_run_id = parent["run_id"]

    # The parent run logs best_config as a tag or param
    best_config_name = parent.get("tags.best_config", "") or parent.get("params.best_config", "")

    if not best_config_name:
        raise RuntimeError(
            f"Parent run '{parent_run_id}' has no 'best_config' tag or param."
        )

    print(f"MLflow parent run: {parent_run_id[:8]} → best_config='{best_config_name}'")

    # Step 3: Find the child run matching best_config_name
    child_runs = mlflow.search_runs(
        experiment_ids=[exp_id],
        filter_string=(
            f"tags.`mlflow.parentRunId` = '{parent_run_id}' "
            f"AND attributes.`run_name` = '{best_config_name}'"
        ),
        max_results=1,
    )

    if child_runs.empty:
        # Fallback: search ALL runs by run_name (in case tag structure differs)
        child_runs = mlflow.search_runs(
            experiment_ids=[exp_id],
            filter_string=f"attributes.`run_name` = '{best_config_name}'",
            order_by=["attributes.start_time DESC"],
            max_results=1,
        )

    if child_runs.empty:
        raise RuntimeError(
            f"No MLflow run found with run_name='{best_config_name}' "
            f"in experiment '{experiment_name}'."
        )

    best_run = child_runs.iloc[0]
    model_name = best_run.get("params.model_name", "")

    if not model_name:
        raise RuntimeError(
            f"MLflow run '{best_config_name}' (run_id: {best_run['run_id']}) "
            f"has no 'model_name' param."
        )

    print(
        f"MLflow child run_name='{best_config_name}' → model_name='{model_name}' "
        f"(run_id: {best_run['run_id'][:8]})"
    )
    return model_name


def _resolve_model_from_label(config_label: str, model_map: dict) -> str:
    """
    Try to resolve model name directly from the Vertex AI config label
    without needing MLflow. The label format is typically:
    'sentence-transformers-all-minilm-l6-v2_dim384_vector'
    """
    for model_name in model_map:
        # Normalize for comparison: 'all-MiniLM-L6-v2' → 'all-minilm-l6-v2'
        normalized = model_name.lower().replace("-", "-")
        label_lower = config_label.lower().replace("-", "-")
        if normalized in label_lower:
            return model_name
    return ""


def get_deployed_embedding_model(config: dict) -> dict:
    """
    Full flow:
      Vertex AI Registry → config label → resolve model_name → dim/column
      Falls back to MLflow lookup if label can't be directly resolved.
    """
    model_map = config["embedding_models"]

    # Step 1: Get config label from Vertex AI
    config_label = _get_config_from_registry(config)

    # Step 2: Try MLflow first for full experiment tracking
    model_name_clean = ""
    try:
        model_name = _get_model_name_from_mlflow(config, config_label)
        model_name_clean = model_name.replace("sentence-transformers/", "")
    except Exception as e:
        print(f"MLflow lookup failed ({e}), falling back to label resolution")

    # Step 3: Fallback — resolve directly from Vertex AI label
    if not model_name_clean:
        model_name_clean = _resolve_model_from_label(config_label, model_map)

    if model_name_clean not in model_map:
        raise ValueError(
            f"Model '{model_name_clean}' not in embedding_models config. "
            f"Known: {list(model_map.keys())}"
        )

    info = model_map[model_name_clean]

    print(
        f"Resolved: {model_name_clean} → "
        f"dim={info['dim']}, column={info['column']}"
    )

    return {
        "model_name": model_name_clean,
        "embedding_dim": info["dim"],
        "embedding_column": info["column"],
    }