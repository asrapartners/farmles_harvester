import dataclasses
from dataclasses import dataclass, field
from typing import Any

STAGE_STATUS_COMPLETED = "completed"
STAGE_STATUS_FAILED = "failed"
STAGE_STATUS_SKIPPED = "skipped"


@dataclass
class StageResult:
    stage_id: str
    stage_number: str
    stage_name: str
    status: str

    consumed_artifacts: list[str] = field(default_factory=list)
    produced_artifacts: list[str] = field(default_factory=list)

    summary_artifact: str | None = None
    error_artifact: str | None = None

    counts: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)
