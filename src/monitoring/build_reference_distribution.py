"""
Build Reference Distribution from Golden Dataset
==================================================
One-time offline script that computes embedding statistics from the
golden eval_queries table in Cloud SQL. These stats serve as the
reference baseline for weekly drift detection.

Outputs (saved as .npz to GCS):
    - centroid: mean vector across all query embeddings (384,)
    - per_dim_mean: per-dimension mean (384,)
    - per_dim_std: per-dimension std (384,)
    - all_embeddings: raw embedding matrix (N, 384) — needed for Evidently
    - metadata: model name, query count, timestamp

Usage:
    # Default: loads from Cloud SQL, uploads to GCS
    python -m src.monitoring.build_reference_distribution

    # Local testing (no GCS upload)
    python -m src.monitoring.build_reference_distribution \
        --skip-gcs-upload --local-backup reference_distribution.npz

Prerequisites:
    pip install sentence-transformers numpy psycopg2-binary google-cloud-storage python-dotenv pyyaml
"""

import argparse
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psycopg2
import yaml
from dotenv import load_dotenv

# ─── Logging ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── Config Loading ───────────────────────────────────────────────────────

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value):
    """Replace ${VAR_NAME} placeholders with environment variable values."""
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            env_val = os.getenv(var_name)
            if env_val is None:
                raise ValueError(
                    f"Environment variable '{var_name}' not set "
                    f"(required by monitoring_config.yaml)"
                )
            return env_val
        return _ENV_VAR_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_config() -> dict:
    """Load monitoring_config.yaml with env var resolution."""
    # .env from project root
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    config_path = Path(__file__).resolve().parent / "config.yaml"
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)
    return _resolve_env_vars(raw)


# ─── Data Loading ──────────────────────────────────────────────────────────

def load_queries_from_cloud_sql(cfg: dict) -> list[str]:
    """Load query texts from the eval_queries table in Cloud SQL."""
    db = cfg["database"]
    db_params = {
        "host": db["host"],
        "port": int(db["port"]),
        "dbname": db["dbname"],
        "user": db["user"],
        "password": db["password"],
    }

    log.info("Connecting to Cloud SQL at %s:%s/%s", db_params["host"], db_params["port"], db_params["dbname"])
    conn = psycopg2.connect(**db_params)

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT query_text from eval_dataset;")
            rows = cur.fetchall()
    finally:
        conn.close()

    queries = [row[0] for row in rows]
    log.info("Loaded %d queries from eval_dataset table", len(queries))
    return queries


# ─── Embedding ─────────────────────────────────────────────────────────────

def compute_embeddings(queries: list[str], cfg: dict) -> np.ndarray:
    """
    Encode all golden dataset queries using the embedding model.
    Returns array of shape (N, embedding_dim).
    """
    from sentence_transformers import SentenceTransformer

    model_name = cfg["embedding"]["model_name"]
    embedding_dim = cfg["embedding"]["dimension"]

    log.info("Loading embedding model: %s", model_name)
    model = SentenceTransformer(model_name)

    log.info("Encoding %d queries...", len(queries))
    embeddings = model.encode(queries, show_progress_bar=True, batch_size=64)
    embeddings = np.array(embeddings, dtype=np.float32)

    assert embeddings.shape == (len(queries), embedding_dim), (
        f"Expected shape ({len(queries)}, {embedding_dim}), got {embeddings.shape}"
    )
    log.info("Embeddings shape: %s", embeddings.shape)
    return embeddings


# ─── Statistics ────────────────────────────────────────────────────────────

def compute_reference_stats(embeddings: np.ndarray) -> dict:
    """Compute reference distribution statistics from the embedding matrix."""
    centroid = embeddings.mean(axis=0)
    per_dim_mean = embeddings.mean(axis=0)
    per_dim_std = embeddings.std(axis=0)

    log.info("Centroid norm: %.4f", np.linalg.norm(centroid))
    log.info("Per-dim std range: [%.4f, %.4f]", per_dim_std.min(), per_dim_std.max())
    log.info("Per-dim std mean: %.4f", per_dim_std.mean())

    return {
        "centroid": centroid,
        "per_dim_mean": per_dim_mean,
        "per_dim_std": per_dim_std,
        "all_embeddings": embeddings,
    }


# ─── Save ──────────────────────────────────────────────────────────────────

def save_to_npz(stats: dict, query_count: int, local_path: str, cfg: dict) -> str:
    """Save reference distribution as a .npz file with metadata."""
    np.savez(
        local_path,
        centroid=stats["centroid"],
        per_dim_mean=stats["per_dim_mean"],
        per_dim_std=stats["per_dim_std"],
        all_embeddings=stats["all_embeddings"],
        model_name=np.array([cfg["embedding"]["model_name"]]),
        embedding_dim=np.array([cfg["embedding"]["dimension"]]),
        query_count=np.array([query_count]),
        created_at=np.array([datetime.now(timezone.utc).isoformat()]),
    )
    log.info("Saved reference distribution to %s", local_path)
    return local_path


def upload_to_gcs(local_path: str, gcs_path: str, cfg: dict):
    """
    Upload the .npz file to GCS.
    Tags the blob with the embedding model name for mismatch detection
    (weekly drift job aborts if model name doesn't match).
    """
    from google.cloud import storage

    bucket_name = cfg["gcs"]["bucket"]
    model_name = cfg["embedding"]["model_name"]

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)

    blob.metadata = {
        "embedding_model": model_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    blob.upload_from_filename(local_path)
    blob.patch()

    log.info("Uploaded to gs://%s/%s", bucket_name, gcs_path)
    log.info("Blob metadata: %s", blob.metadata)


# ─── Validation ────────────────────────────────────────────────────────────

def validate_npz(local_path: str, cfg: dict):
    """Reload the .npz and verify shapes and metadata."""
    embedding_dim = cfg["embedding"]["dimension"]

    log.info("Validating saved .npz...")
    data = np.load(local_path, allow_pickle=False)

    assert data["centroid"].shape == (embedding_dim,), f"centroid shape: {data['centroid'].shape}"
    assert data["per_dim_mean"].shape == (embedding_dim,)
    assert data["per_dim_std"].shape == (embedding_dim,)
    assert data["all_embeddings"].shape[1] == embedding_dim

    query_count = int(data["query_count"][0])
    model_name = str(data["model_name"][0])

    log.info(
        "Validation passed — model=%s, queries=%d, dims=%d",
        model_name, query_count, embedding_dim,
    )


# ─── CLI ───────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Build reference embedding distribution from golden dataset (Cloud SQL)",
    )
    parser.add_argument(
        "--output-gcs-path",
        default=None,
        help="GCS blob path (default: from monitoring_config.yaml)",
    )
    parser.add_argument(
        "--local-backup",
        default=None,
        help="Optional: save a local copy of the .npz file at this path",
    )
    parser.add_argument(
        "--skip-gcs-upload",
        action="store_true",
        help="Skip GCS upload (local-only mode for testing)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config()

    gcs_path = args.output_gcs_path or cfg["gcs"]["reference_distribution_path"]

    # 1. Load queries from Cloud SQL
    queries = load_queries_from_cloud_sql(cfg)

    if len(queries) < 10:
        log.error("Only %d queries found — too few for a meaningful reference distribution.", len(queries))
        sys.exit(1)

    log.info("Golden dataset: %d queries", len(queries))

    # 2. Compute embeddings
    embeddings = compute_embeddings(queries, cfg)

    # 3. Compute reference statistics
    stats = compute_reference_stats(embeddings)

    # 4. Save to local .npz
    if args.local_backup:
        local_path = args.local_backup
    else:
        local_path = os.path.join(tempfile.gettempdir(), "reference_distribution.npz")

    save_to_npz(stats, query_count=len(queries), local_path=local_path, cfg=cfg)

    # 5. Validate
    validate_npz(local_path, cfg)

    # 6. Upload to GCS
    if not args.skip_gcs_upload:
        upload_to_gcs(local_path, gcs_path, cfg)
    else:
        log.info("Skipped GCS upload (--skip-gcs-upload)")

    # Cleanup temp file if no local backup requested
    if not args.local_backup and os.path.exists(local_path):
        os.remove(local_path)
        log.info("Cleaned up temp file")

    log.info("Done. Reference distribution ready for drift detection.")


if __name__ == "__main__":
    main()