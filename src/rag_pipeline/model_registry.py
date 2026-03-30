"""
Fetches the deployed embedding model config from Vertex AI Model Registry.
"""

from google.cloud import aiplatform


def get_deployed_embedding_model(config: dict) -> dict:
    """
    Query Vertex AI for the latest registered model and extract
    the embedding model name from its labels.

    Returns:
        dict with keys: model_name, embedding_dim, embedding_column
    """
    gcp = config["gcp"]
    model_map = config["embedding_models"]

    aiplatform.init(project=gcp["project_id"], location=gcp["region"])

    models = aiplatform.Model.list(
        filter=f'display_name="{gcp["model_registry_name"]}"',
        order_by="update_time desc",
    )

    if not models:
        raise RuntimeError(
            f"No model found in Vertex AI registry with name "
            f"'{gcp['model_registry_name']}'. Run the eval pipeline first."
        )

    latest = models[0]
    labels = latest.labels or {}
    model_name = labels.get("embedding_model", "all-MiniLM-L6-v2")

    if model_name not in model_map:
        raise ValueError(
            f"Unknown embedding model from registry: {model_name}. "
            f"Known models: {list(model_map.keys())}"
        )

    info = model_map[model_name]
    print(f"Loaded from Vertex AI registry: {model_name} (version: {latest.version_id})")

    return {
        "model_name": model_name,
        "embedding_dim": info["dim"],
        "embedding_column": info["column"],
    }