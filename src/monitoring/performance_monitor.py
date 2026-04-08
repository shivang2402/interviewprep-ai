"""
Weekly Performance Monitor — Evidently Drift Trigger
=====================================================
Runs as a GitHub Actions cron job (every Monday 10 AM UTC).

Pulls production query embeddings from the last 7 days, runs an Evidently
DataDriftReport treating each embedding dimension as a feature, and triggers
a corpus refresh if more than 30% of dimensions are flagged as drifted.

The 30% threshold is read from:
    src/evaluation/retraining_thresholds.yaml
        retraining_triggers.evidently_drift_pct

This gives the Evidently drift threshold a standalone, auditable trigger path
(separate from the composite check in drift_detection.py which requires any
two of three metrics to breach).

Steps:
    1. Load evidently_drift_pct from retraining_thresholds.yaml
    2. Pull production query embeddings from query_logs (last N days)
    3. Load reference distribution from GCS
    4. Run Evidently DataDriftReport on all embedding dimensions
    5. If drift_pct > threshold → dispatch corpus_refresh.yml via GitHub API
    6. Log results to MLflow (monitoring experiment)

Usage:
    python -m src.monitoring.performance_monitor
    python -m src.monitoring.performance_monitor --dry-run
    python -m src.monitoring.performance_monitor --days 14

Prerequisites:
    pip install sentence-transformers numpy psycopg2-binary evidently pandas \
        google-cloud-storage mlflow pyyaml requests python-dotenv
"""

import argparse
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mlflow
import requests
import yaml

from src.monitoring.utils import load_config, get_db_params
from src.monitoring.drift_detection import (
    pull_production_embeddings,
    load_reference_distribution,
    compute_evidently_drift,
)

# ─── Logging ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Step 1 — Load retraining threshold
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# Step 4 — Evaluate Evidently drift against threshold
# ═══════════════════════════════════════════════════════════════════════════

def check_evidently_threshold(evidently_pct: float, threshold: float) -> bool:
    """
    Returns True if the fraction of drifted embedding dimensions exceeds
    the configured threshold (from retraining_thresholds.yaml).
    """
    if evidently_pct > threshold:
        log.warning(
            "EVIDENTLY DRIFT THRESHOLD BREACHED — %.2f%% of features drifted "
            "(threshold: %.0f%%) → corpus refresh required",
            evidently_pct * 100,
            threshold * 100,
        )
        return True

    log.info(
        "Evidently drift within threshold — %.2f%% of features drifted "
        "(threshold: %.0f%%)",
        evidently_pct * 100,
        threshold * 100,
    )
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Step 6 — Log to MLflow
# ═══════════════════════════════════════════════════════════════════════════

def log_to_mlflow(
    evidently_pct: float,
    threshold: float,
    drift_triggered: bool,
    prod_query_count: int,
    html_report_path: str,
    mlflow_uri: str,
    week_start: str,
):
    """
    Log Evidently drift check results to the 'monitoring' MLflow experiment.
    Tags: run_type=evidently_drift_check, week_start=YYYY-MM-DD
    """
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment("monitoring")

    with mlflow.start_run(run_name=f"evidently_drift_check_{week_start}"):
        mlflow.set_tag("run_type", "evidently_drift_check")
        mlflow.set_tag("week_start", week_start)

        mlflow.log_metric("evidently_drift_pct", evidently_pct)
        mlflow.log_metric("evidently_drift_threshold", threshold)
        mlflow.log_metric("production_query_count", prod_query_count)
        mlflow.log_metric("corpus_refresh_triggered", 1 if drift_triggered else 0)

        if html_report_path and os.path.exists(html_report_path):
            mlflow.log_artifact(html_report_path, artifact_path="drift_reports")

    log.info("Logged Evidently drift check to MLflow (week_start=%s)", week_start)


# ═══════════════════════════════════════════════════════════════════════════
# Step 5 — Trigger corpus refresh
# ═══════════════════════════════════════════════════════════════════════════

def trigger_corpus_refresh(evidently_pct: float):
    """
    Dispatch corpus_refresh.yml via GitHub API.
    Requires GITHUB_TOKEN and GITHUB_REPO env vars.
    """
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")

    if not token or not repo:
        log.warning("GITHUB_TOKEN or GITHUB_REPO not set — skipping corpus refresh trigger")
        return

    url = f"https://api.github.com/repos/{repo}/actions/workflows/corpus_refresh.yml/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "ref": "main",
        "inputs": {
            "trigger_reason": "evidently_drift_threshold_breached",
            "trigger_source": "performance_monitor",
            "evidently_drift_pct": f"{evidently_pct:.4f}",
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code == 204:
        log.info(
            "Triggered corpus_refresh.yml (evidently_drift=%.2f%%)",
            evidently_pct * 100,
        )
    else:
        log.error(
            "Failed to trigger corpus_refresh: %s %s",
            resp.status_code, resp.text,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Weekly Evidently drift threshold check — triggers corpus refresh if >threshold% of embedding features drifted"
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="Look-back window for production query embeddings (default: 7)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute metrics and log to MLflow only — do not trigger corpus refresh",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config()

    week_start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    log.info("Evidently drift check for week starting %s (%d-day window)", week_start, args.days)

    # ── Step 1: Load threshold from retraining_thresholds.yaml ────────────
    retraining_cfg = load_retraining_thresholds()
    threshold = retraining_cfg["retraining_triggers"]["evidently_drift_pct"]
    log.info(
        "Evidently drift threshold (from retraining_thresholds.yaml): %.0f%%",
        threshold * 100,
    )

    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://136.109.222.133:5000")

    # ── Step 2: Pull production query embeddings ───────────────────────────
    prod_embeddings = pull_production_embeddings(cfg, days=args.days)
    prod_query_count = len(prod_embeddings)

    min_queries = cfg["drift_thresholds"]["min_production_queries"]
    if prod_query_count < min_queries:
        log.warning(
            "Only %d production queries (minimum: %d) — skipping Evidently drift check",
            prod_query_count, min_queries,
        )
        log_to_mlflow(
            evidently_pct=0.0, threshold=threshold,
            drift_triggered=False, prod_query_count=prod_query_count,
            html_report_path="", mlflow_uri=mlflow_uri, week_start=week_start,
        )
        log.info("Done (skipped — low query volume)")
        return

    # ── Step 3: Load reference distribution from GCS ──────────────────────
    ref = load_reference_distribution(cfg)

    # ── Step 4: Run Evidently DataDriftReport ──────────────────────────────
    evidently_pct, html_report = compute_evidently_drift(
        prod_embeddings, ref["all_embeddings"], cfg
    )

    # Save HTML report for MLflow artifact upload
    html_report_path = os.path.join(
        tempfile.gettempdir(), f"evidently_drift_{week_start}.html"
    )
    with open(html_report_path, "w") as f:
        f.write(html_report)

    drift_triggered = check_evidently_threshold(evidently_pct, threshold)

    # ── Step 6: Log to MLflow ──────────────────────────────────────────────
    log_to_mlflow(
        evidently_pct=evidently_pct,
        threshold=threshold,
        drift_triggered=drift_triggered,
        prod_query_count=prod_query_count,
        html_report_path=html_report_path,
        mlflow_uri=mlflow_uri,
        week_start=week_start,
    )

    # ── Step 5: Trigger corpus refresh if threshold breached ───────────────
    if drift_triggered and not args.dry_run:
        trigger_corpus_refresh(evidently_pct)
    elif args.dry_run:
        log.info("Dry run — skipping corpus refresh trigger")

    # Cleanup
    if os.path.exists(html_report_path):
        os.remove(html_report_path)

    log.info("Done. drift_triggered=%s", drift_triggered)


if __name__ == "__main__":
    main()
