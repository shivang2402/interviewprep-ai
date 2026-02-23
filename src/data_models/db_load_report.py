# ─────────────────────────────────────────────────
# DB load run report
# ─────────────────────────────────────────────────
"""
Report for a single BatchDBLoader run. Created after each load_batch,
serialized to JSON, and stored in GCS (e.g. db-report/) for audit.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class DBLoadReport:
    """
    Summary of a DB load run (success/failure counts and per-item lists).
    Built from BatchDBLoader.load_batch() result; written to bucket after each run.
    """

    report_type: str = "db_load"
    completed_at: str = ""
    source_prefix: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)
    success: Dict[str, Any] = field(default_factory=dict)
    failures: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_load_summary(cls, summary: Dict[str, Any], source_prefix: str) -> "DBLoadReport":
        """Build a report from a load_batch() summary dict."""
        total = summary.get("total", 0)
        inserted = summary.get("inserted", 0)
        skipped = summary.get("skipped", 0)
        success_list: List[Dict[str, Any]] = summary.get("success", [])
        failed_reads: List[Dict[str, Any]] = summary.get("failed_reads", [])
        failed_inserts: List[Dict[str, Any]] = summary.get("failed_inserts", [])

        return cls(
            completed_at=datetime.now(timezone.utc).isoformat(),
            source_prefix=source_prefix,
            summary={
                "total": total,
                "success_count": inserted,
                "failure_count": skipped,
                "inserted": inserted,
                "skipped": skipped,
            },
            success={"count": len(success_list), "items": success_list},
            failures={
                "read_errors": {"count": len(failed_reads), "items": failed_reads},
                "insert_errors": {"count": len(failed_inserts), "items": failed_inserts},
            },
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def report_filename(self) -> str:
        """Timestamp-based filename for this report (no path)."""
        ts = self.completed_at.replace(":", "").replace("-", "")[:15]
        return f"db_load_{ts}.json"
