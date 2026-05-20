from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StagePaths:
    output_path: Path
    summary_path: Path
    errors_path: Path

    @classmethod
    def for_stage(cls, run_dir: Path, stage_number: str, artifact_name: str) -> "StagePaths":
        base = run_dir.resolve()
        return cls(
            output_path=base / f"{stage_number}_{artifact_name}.jsonl",
            summary_path=base / f"{stage_number}_{artifact_name}_summary.json",
            errors_path=base / f"{stage_number}_{artifact_name}_errors.jsonl",
        )
