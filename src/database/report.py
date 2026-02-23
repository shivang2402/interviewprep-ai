"""Build and structure load-run reports for upload to GCS."""

from datetime import datetime, timezone
from typing import Any


def build_load_report(summary: dict[str, Any], source_prefix: str) -> dict[str, Any]:
    """
    Build a JSON-serializable report from a load_batch summary.
    Includes named lists of successes and failures (path, document_id, title).
    """
    total = summary.get("total", 0)
    inserted = summary.get("inserted", 0)
    skipped = summary.get("skipped", 0)
    success_list = summary.get("success", [])
    failed_reads = summary.get("failed_reads", [])
    failed_inserts = summary.get("failed_inserts", [])

    return {
        "report_type": "db_load",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "source_prefix": source_prefix,
        "summary": {
            "total": total,
            "success_count": inserted,
            "failure_count": skipped,
            "inserted": inserted,
            "skipped": skipped,
        },
        "success": {
            "count": len(success_list),
            "items": success_list,
        },
        "failures": {
            "read_errors": {
                "count": len(failed_reads),
                "items": failed_reads,
            },
            "insert_errors": {
                "count": len(failed_inserts),
                "items": failed_inserts,
            },
        },
    }
