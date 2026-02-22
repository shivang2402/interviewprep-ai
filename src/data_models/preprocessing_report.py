# ─────────────────────────────────────────────────
# Pipeline Run Report
# ─────────────────────────────────────────────────
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any


@dataclass
class PreprocessingPipelineReport:
    """
    Summary of a full pipeline run.

    Written to GCS alongside processed output for audit trail.
    """

    batch_id: str
    started_at: str = ""
    completed_at: str = ""
    total_duration_seconds: float = 0.0
    input_count: int = 0
    output_count: int = 0
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    resumed_from_step: Optional[str] = None
    quarantined_count: int = 0
    status: str = "pending"  # pending | completed | failed

    def to_dict(self) -> dict:
        return asdict(self)