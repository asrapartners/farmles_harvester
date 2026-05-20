from dataclasses import dataclass
from pathlib import Path


@dataclass
class StagePaths:
    output_path: Path
    summary_path: Path
    errors_path: Path

    @classmethod
    def for_stage(cls, run_dir: Path, stage_number: str, artifact_name: str) -> "StagePaths":
        return cls(
            output_path=run_dir / f"{stage_number}_{artifact_name}.jsonl",
            summary_path=run_dir / f"{stage_number}_{artifact_name}_summary.json",
            errors_path=run_dir / f"{stage_number}_{artifact_name}_errors.jsonl",
        )
