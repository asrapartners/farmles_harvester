import json
from pathlib import Path

from farmles_harvester.pipeline.stage_result import StageResult


def create_initial_manifest(
    run_id: str,
    tag: str,
    seed_file_snapshot: str,
    created_at: str,
) -> dict:
    return {
        "run_id": run_id,
        "created_at": created_at,
        "tag": tag,
        "seed_file_snapshot": seed_file_snapshot,
        "stages": {},
        "execution_log": [],
    }


def record_stage_result(manifest: dict, stage_result: StageResult) -> None:
    manifest["stages"][stage_result.stage_id] = stage_result.to_dict()
    sequence = len(manifest["execution_log"]) + 1
    manifest["execution_log"].append({
        "sequence": sequence,
        "stage_id": stage_result.stage_id,
        "status": stage_result.status,
        "started_at": stage_result.started_at,
        "completed_at": stage_result.completed_at,
    })


def write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
