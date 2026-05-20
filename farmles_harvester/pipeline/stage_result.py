import dataclasses
from dataclasses import dataclass


@dataclass
class StageResult:
    stage_id: str
    stage_number: str
    stage_name: str
    status: str  # "completed" | "failed"
    consumed_artifacts: list[str]
    produced_artifacts: list[str]
    summary_artifact: str
    error_artifact: str
    counts: dict
    started_at: str
    completed_at: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)
