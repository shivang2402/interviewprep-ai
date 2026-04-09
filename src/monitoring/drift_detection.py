"""
Weekly Drift Detection Pipeline
=================================
Runs as a GitHub Actions cron job (every Monday 9 AM UTC).
Computes drift between production query embeddings and the golden
dataset reference distribution, logs results to MLflow, and triggers
corpus refresh if drift is detected.

Steps covered:
    Step 4 — Pull production queries, load reference, compute 3 drift metrics
    Step 5 — Log metrics + Evidently HTML report to MLflow
    Step 6 — Threshold check → trigger corpus_refresh.yml + Slack notification

Usage:
    # Weekly cron (GitHub Actions or manual)
    python -m src.monitoring.drift_detection

    # Dry run (no trigger, no Slack)
    python -m src.monitoring.drift_detection --dry-run

    # Custom date range
    python -m src.monitoring.drift_detection --days 14

Prerequisites:
    pip install sentence-transformers numpy psycopg2-binary google-cloud-storage \
        python-dotenv pyyaml mlflow evidently pandas scipy requests
"""

import argparse
import io
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import psycopg2
import yaml
from scipy.spatial.distance import cosine as cosine_distance

from src.monitoring.utils import load_config, get_db_params

# ─── Retraining threshold loader ───────────────────────────────────────────

def load_retraining_thresholds() -> dict:
    """
    Load retraining trigger thresholds from
    src/evaluation/retraining_thresholds.yaml (version-controlled alongside
    retrieval_model_configs.yaml for auditability).
    """
    config_path = (
        Path(__file__).resolve().parents[1]
        / "evaluation"
        / "retraining_thresholds.yaml"
    )
    with open(config_path) as f:
        return yaml.safe_load(f)

# ─── Logging ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4a — Pull Production Queries from Last N Days
# ═══════════════════════════════════════════════════════════════════════════

def pull_production_embeddings(cfg: dict, days: int) -> np.ndarray:
    """
    Query the query_log table for embeddings from the last N days.
    Returns array of shape (N, embedding_dim) or empty array.
    """
    db_params = get_db_params(cfg)
    conn = psycopg2.connect(**db_params)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT query_embedding
                FROM query_logs
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                  AND query_embedding IS NOT NULL;
                """,
                (days,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return np.array([])

    # pgvector returns embeddings as strings like "[0.1, 0.2, ...]"
    embeddings = []
    for row in rows:
        emb = row[0]
        if isinstance(emb, str):
            emb = np.fromstring(emb.strip("[]"), sep=",", dtype=np.float32)
        elif isinstance(emb, (list, tuple)):
            emb = np.array(emb, dtype=np.float32)
        else:
            emb = np.array(emb, dtype=np.float32)
        embeddings.append(emb)

    result = np.stack(embeddings)
    log.info("Pulled %d production embeddings from last %d days", len(result), days)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4b — Load Reference Distribution from GCS
# ═══════════════════════════════════════════════════════════════════════════

def load_reference_distribution(cfg: dict) -> dict:
    """
    Download reference_distribution.npz from GCS.
    Validates embedding model matches config to prevent mismatch.
    Returns dict with centroid, per_dim_mean, per_dim_std, all_embeddings.
    """
    from google.cloud import storage

    bucket_name = cfg["gcs"]["bucket"]
    gcs_path = cfg["gcs"]["reference_distribution_path"]

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)

    if not blob.exists():
        log.error("Reference distribution not found at gs://%s/%s", bucket_name, gcs_path)
        log.error("Run build_reference_distribution.py first.")
        sys.exit(1)

    # Check embedding model mismatch (edge case from spec)
    blob.reload()
    blob_model = (blob.metadata or {}).get("embedding_model", "")
    config_model = cfg["embedding"]["model_name"]
    if blob_model and blob_model != config_model:
        log.error(
            "Embedding model mismatch: reference was built with '%s' but config specifies '%s'. "
            "Regenerate the reference distribution.",
            blob_model, config_model,
        )
        sys.exit(1)

    # Download to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".npz", delete=False)
    blob.download_to_filename(tmp.name)

    data = np.load(tmp.name, allow_pickle=False)
    os.unlink(tmp.name)

    log.info(
        "Loaded reference distribution: model=%s, queries=%d",
        str(data["model_name"][0]), int(data["query_count"][0]),
    )

    return {
        "centroid": data["centroid"],
        "per_dim_mean": data["per_dim_mean"],
        "per_dim_std": data["per_dim_std"],
        "all_embeddings": data["all_embeddings"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4c — Compute Drift Metrics
# ═══════════════════════════════════════════════════════════════════════════

def compute_centroid_cosine_distance(
    prod_embeddings: np.ndarray, ref_centroid: np.ndarray
) -> float:
    """
    Cosine distance between production centroid and reference centroid.
    Range 0–2, where 0 = identical centroids.
    """
    prod_centroid = prod_embeddings.mean(axis=0)
    distance = float(cosine_distance(prod_centroid, ref_centroid))
    log.info("Centroid cosine distance: %.6f", distance)
    return distance


def compute_per_dim_shift(
    prod_embeddings: np.ndarray,
    ref_per_dim_mean: np.ndarray,
    ref_per_dim_std: np.ndarray,
) -> float:
    """
    For each dimension, compute |prod_mean - ref_mean| / ref_std.
    Returns the 95th percentile across all dimensions.
    Flags if this exceeds the threshold (default: 2.0 std).
    """
    prod_mean = prod_embeddings.mean(axis=0)
    # Avoid division by zero for near-constant dimensions
    safe_std = np.where(ref_per_dim_std > 1e-8, ref_per_dim_std, 1e-8)
    shifts = np.abs(prod_mean - ref_per_dim_mean) / safe_std
    p95 = float(np.percentile(shifts, 95))
    log.info("Per-dim shift p95: %.4f (max: %.4f)", p95, float(shifts.max()))
    return p95


def compute_evidently_drift(
    prod_embeddings: np.ndarray,
    ref_embeddings: np.ndarray,
    cfg: dict,
) -> tuple[float, str]:
    """
    Run Evidently DataDriftReport treating each embedding dimension as a feature.
    Returns (drift_pct, html_report_string).
    drift_pct = fraction of dimensions flagged as drifted.
    """
    from evidently.report import Report
    from evidently.metric_preset import DataDriftPreset

    embedding_dim = cfg["embedding"]["dimension"]
    col_names = [f"dim_{i}" for i in range(embedding_dim)]

    ref_df = pd.DataFrame(ref_embeddings, columns=col_names)
    prod_df = pd.DataFrame(prod_embeddings, columns=col_names)

    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=ref_df, current_data=prod_df)

    # Extract drift share from report
    report_dict = report.as_dict()
    # Navigate Evidently's result structure
    drift_share = 0.0
    for metric_result in report_dict.get("metrics", []):
        result = metric_result.get("result", {})
        if "share_of_drifted_columns" in result:
            drift_share = result["share_of_drifted_columns"]
            break

    log.info("Evidently drift: %.2f%% of dimensions drifted", drift_share * 100)

    # Generate HTML report
    html_buffer = io.StringIO()
    report.save_html(html_buffer)
    html_report = html_buffer.getvalue()

    return drift_share, html_report


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4d — Aggregate Into Composite Drift Flag
# ═══════════════════════════════════════════════════════════════════════════

def evaluate_drift(
    centroid_dist: float,
    p95_dim_shift: float,
    evidently_pct: float,
    cfg: dict,
    evidently_threshold: float,
) -> tuple[bool, list[str]]:
    """
    Composite drift flag: drift is detected if ANY TWO of the three metrics
    breach their threshold. Single breaches are logged as warnings.

    centroid_cosine_distance and per_dim_shift_std thresholds come from
    src/monitoring/config.yaml (operational tuning parameters).
    evidently_threshold comes from src/evaluation/retraining_thresholds.yaml
    so it is version-controlled alongside the retrieval eval config.

    Returns (drift_detected, list_of_breached_metric_names).
    """
    thresholds = cfg["drift_thresholds"]
    breaches = []

    if centroid_dist > thresholds["centroid_cosine_distance"]:
        breaches.append(f"centroid_cosine_distance ({centroid_dist:.4f} > {thresholds['centroid_cosine_distance']})")

    if p95_dim_shift > thresholds["per_dim_shift_std"]:
        breaches.append(f"per_dim_shift_p95 ({p95_dim_shift:.4f} > {thresholds['per_dim_shift_std']})")

    if evidently_pct > evidently_threshold:
        breaches.append(f"evidently_drift_pct ({evidently_pct:.2%} > {evidently_threshold:.0%})")

    drift_detected = len(breaches) >= 2

    if drift_detected:
        log.warning("DRIFT DETECTED — %d thresholds breached: %s", len(breaches), breaches)
    elif breaches:
        log.warning("Single threshold breach (warning only): %s", breaches)
    else:
        log.info("No drift detected — all metrics within thresholds")

    return drift_detected, breaches


# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — Log to MLflow
# ═══════════════════════════════════════════════════════════════════════════

def log_to_mlflow(
    centroid_dist: float,
    p95_dim_shift: float,
    evidently_pct: float,
    prod_query_count: int,
    drift_detected: bool,
    html_report_path: str,
    cfg: dict,
    week_start: str,
):
    """
    Log drift metrics to MLflow under the 'monitoring' experiment.
    Tags: run_type=drift_detection, week_start=YYYY-MM-DD
    """
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", f"http://136.109.222.133:5000")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(cfg["mlflow"]["experiment_name"])

    run = mlflow.start_run(run_name=f"drift_detection_{week_start}")
    try:
        mlflow.set_tag("run_type", "drift_detection")
        mlflow.set_tag("week_start", week_start)

        mlflow.log_metric("centroid_cosine_distance", centroid_dist)
        mlflow.log_metric("p95_dimension_shift", p95_dim_shift)
        mlflow.log_metric("evidently_drift_pct", evidently_pct)
        mlflow.log_metric("production_query_count", prod_query_count)
        mlflow.log_metric("drift_detected", 1 if drift_detected else 0)

        # Log Evidently HTML report as artifact
        if html_report_path and os.path.exists(html_report_path):
            mlflow.log_artifact(html_report_path, artifact_path="drift_reports")

        log.info("Logged drift metrics to MLflow (run_id=%s)", run.info.run_id)
    finally:
        mlflow.end_run()


# ═══════════════════════════════════════════════════════════════════════════
# STEP 6 — Threshold Check, Trigger, and Notifications
# ═══════════════════════════════════════════════════════════════════════════

def upload_evidently_report_to_gcs(html_content: str, cfg: dict, week_start: str) -> str:
    """Save Evidently HTML report to GCS for auditability."""
    from google.cloud import storage

    bucket_name = cfg["gcs"]["bucket"]
    gcs_path = f"{cfg['gcs']['drift_reports_prefix']}/{week_start}.html"

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(html_content, content_type="text/html")

    log.info("Uploaded Evidently report to gs://%s/%s", bucket_name, gcs_path)
    return f"gs://{bucket_name}/{gcs_path}"


def trigger_corpus_refresh(drift_scores: dict):
    """
    Fire a workflow_dispatch event to GitHub Actions corpus_refresh.yml.
    Requires GITHUB_TOKEN and GITHUB_REPO env vars.
    """
    import requests

    token = os.getenv("GITHUB_TOKEN")
    repo = "https://github.com/shreycshah/interviewprep-ai"

    if not token:
        log.warning("GITHUB_TOKEN not set — skipping corpus refresh trigger")
        return

    url = f"https://api.github.com/repos/{repo}/actions/workflows/corpus_refresh.yml/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "ref": "main",
        "inputs": {
            "trigger_reason": "drift_detection",
            "centroid_distance": str(drift_scores["centroid_cosine_distance"]),
            "evidently_drift_pct": str(drift_scores["evidently_drift_pct"]),
            "p95_dim_shift": str(drift_scores["p95_dimension_shift"]),
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code == 204:
        log.info("Triggered corpus_refresh.yml workflow")
    else:
        log.error("Failed to trigger corpus_refresh: %s %s", resp.status_code, resp.text)


# def send_slack_notification(
#     drift_detected: bool,
#     breaches: list[str],
#     scores: dict,
#     prod_query_count: int,
# ):
#     """
#     Post drift check result to Slack via webhook.
#     Requires SLACK_WEBHOOK_URL env var.
#     """
#     import requests

#     webhook_url = os.getenv("SLACK_WEBHOOK_URL")
#     if not webhook_url:
#         log.warning("SLACK_WEBHOOK_URL not set — skipping Slack notification")
#         return

#     if drift_detected:
#         emoji = ":rotating_light:"
#         title = "Drift Detected — Corpus Refresh Triggered"
#         color = "#FF0000"
#         detail = "Breached thresholds:\n" + "\n".join(f"• {b}" for b in breaches)
#     else:
#         emoji = ":white_check_mark:"
#         title = "Weekly Drift Check Passed"
#         color = "#36A64F"
#         detail = "All metrics within thresholds."

#     payload = {
#         "attachments": [
#             {
#                 "color": color,
#                 "blocks": [
#                     {
#                         "type": "header",
#                         "text": {"type": "plain_text", "text": f"{emoji} {title}"},
#                     },
#                     {
#                         "type": "section",
#                         "fields": [
#                             {"type": "mrkdwn", "text": f"*Centroid Distance:*\n{scores['centroid_cosine_distance']:.6f}"},
#                             {"type": "mrkdwn", "text": f"*P95 Dim Shift:*\n{scores['p95_dimension_shift']:.4f}"},
#                             {"type": "mrkdwn", "text": f"*Evidently Drift %:*\n{scores['evidently_drift_pct']:.2%}"},
#                             {"type": "mrkdwn", "text": f"*Production Queries:*\n{prod_query_count}"},
#                         ],
#                     },
#                     {
#                         "type": "section",
#                         "text": {"type": "mrkdwn", "text": detail},
#                     },
#                 ],
#             }
#         ]
#     }

#     resp = requests.post(webhook_url, json=payload, timeout=10)
#     if resp.status_code == 200:
#         log.info("Slack notification sent")
#     else:
#         log.error("Slack notification failed: %s %s", resp.status_code, resp.text)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(description="Weekly drift detection pipeline")
    parser.add_argument("--days", type=int, default=7, help="Look-back window in days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Compute metrics only — no trigger, no Slack")
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config()

    # Load evidently_drift_pct from the version-controlled retraining thresholds
    # (src/evaluation/retraining_thresholds.yaml) so both retraining triggers
    # are auditable in the same place.
    retraining_cfg = load_retraining_thresholds()
    evidently_threshold = retraining_cfg["retraining_triggers"]["evidently_drift_pct"]
    log.info("Evidently drift threshold (from retraining_thresholds.yaml): %.0f%%", evidently_threshold * 100)

    week_start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    log.info("Drift detection for week starting %s (%d-day window)", week_start, args.days)

    # ── Step 4a: Pull production embeddings ────────────────────────────────
    prod_embeddings = pull_production_embeddings(cfg, days=args.days)
    prod_query_count = len(prod_embeddings)

    # Edge case: low query volume
    min_queries = cfg["drift_thresholds"]["min_production_queries"]
    if prod_query_count < min_queries:
        log.warning(
            "Only %d production queries (minimum: %d) — skipping drift computation",
            prod_query_count, min_queries,
        )
        # Still log to MLflow so the skip is visible
        log_to_mlflow(
            centroid_dist=0.0, p95_dim_shift=0.0, evidently_pct=0.0,
            prod_query_count=prod_query_count, drift_detected=False,
            html_report_path="", cfg=cfg, week_start=week_start,
        )
        # send_slack_notification(
        #     drift_detected=False, breaches=[],
        #     scores={"centroid_cosine_distance": 0, "p95_dimension_shift": 0, "evidently_drift_pct": 0},
        #     prod_query_count=prod_query_count,
        # )
        log.info("Done (skipped — low volume)")
        return

    # ── Step 4b: Load reference distribution ───────────────────────────────
    ref = load_reference_distribution(cfg)

    # ── Step 4c: Compute drift metrics ─────────────────────────────────────
    centroid_dist = compute_centroid_cosine_distance(prod_embeddings, ref["centroid"])
    p95_dim_shift = compute_per_dim_shift(prod_embeddings, ref["per_dim_mean"], ref["per_dim_std"])
    evidently_pct, html_report = compute_evidently_drift(prod_embeddings, ref["all_embeddings"], cfg)

    scores = {
        "centroid_cosine_distance": centroid_dist,
        "p95_dimension_shift": p95_dim_shift,
        "evidently_drift_pct": evidently_pct,
    }

    # ── Step 4d: Evaluate composite drift flag ─────────────────────────────
    drift_detected, breaches = evaluate_drift(centroid_dist, p95_dim_shift, evidently_pct, cfg, evidently_threshold)

    # ── Save Evidently HTML report locally (for MLflow artifact) ───────────
    html_report_path = os.path.join(tempfile.gettempdir(), f"drift_report_{week_start}.html")
    with open(html_report_path, "w") as f:
        f.write(html_report)

    # ── Step 5: Log to MLflow ──────────────────────────────────────────────
    log_to_mlflow(
        centroid_dist=centroid_dist,
        p95_dim_shift=p95_dim_shift,
        evidently_pct=evidently_pct,
        prod_query_count=prod_query_count,
        drift_detected=drift_detected,
        html_report_path=html_report_path,
        cfg=cfg,
        week_start=week_start,
    )

    # ── Upload Evidently report to GCS ─────────────────────────────────────
    upload_evidently_report_to_gcs(html_report, cfg, week_start)

    # ── Step 6: Trigger and notify ─────────────────────────────────────────
    if not args.dry_run:
        if drift_detected:
            trigger_corpus_refresh(scores)
        # send_slack_notification(drift_detected, breaches, scores, prod_query_count)
    else:
        log.info("Dry run — skipping trigger and Slack notification")

    # Cleanup
    if os.path.exists(html_report_path):
        os.remove(html_report_path)

    log.info("Done. drift_detected=%s", drift_detected)


if __name__ == "__main__":
    main()