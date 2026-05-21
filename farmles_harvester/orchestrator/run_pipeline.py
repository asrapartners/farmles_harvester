import shutil
from datetime import datetime, timezone
from pathlib import Path

from farmles_harvester.orchestrator.exceptions import PipelineError
from farmles_harvester.orchestrator.manifest import (
    create_initial_manifest,
    record_stage_result,
    write_manifest,
)
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.stages.discover_links import run_discover_links
from farmles_harvester.stages.generate_markdown_pages import run_generate_markdown_pages
from farmles_harvester.stages.normalize_source_leads import run_normalize_source_leads
from farmles_harvester.stages.score_candidate_urls import run_score_candidate_urls
from farmles_harvester.stages.validate_urls import run_validate_urls


def run_pipeline(
    seed_file: Path,
    tag: str,
    runs_dir: Path,
    config: dict | None = None,
    fetcher=None,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    run_id = f"{timestamp}_{tag}"
    run_dir = runs_dir / run_id

    if run_dir.exists():
        raise FileExistsError(f"Run folder already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    seed_snapshot = run_dir / "seed_urls.txt"
    shutil.copy2(seed_file, seed_snapshot)

    created_at = datetime.now(timezone.utc).isoformat()
    manifest = create_initial_manifest(
        run_id=run_id,
        tag=tag,
        seed_file_snapshot="seed_urls.txt",
        created_at=created_at,
    )
    manifest_path = run_dir / "manifest.json"
    write_manifest(manifest_path, manifest)

    def _record_and_check(result: StageResult) -> None:
        record_stage_result(manifest, result)
        write_manifest(manifest_path, manifest)
        if result.status != STAGE_STATUS_COMPLETED:
            raise PipelineError(
                f"Stage {result.stage_id} failed with status '{result.status}'",
                stage_id=result.stage_id,
                run_dir=run_dir,
            )

    paths_00 = StagePaths.for_stage(run_dir, "00", "normalized_source_leads")
    _record_and_check(run_normalize_source_leads(
        input_path=seed_snapshot,
        stage_paths=paths_00,
        run_id=run_id,
        config=config,
    ))

    paths_01 = StagePaths.for_stage(run_dir, "01", "validated_sources")
    _record_and_check(run_validate_urls(
        input_path=paths_00.output_path,
        stage_paths=paths_01,
        run_id=run_id,
        config=config,
        fetcher=fetcher,
    ))

    paths_02 = StagePaths.for_stage(run_dir, "02", "discovered_links")
    _record_and_check(run_discover_links(
        input_path=paths_01.output_path,
        stage_paths=paths_02,
        run_id=run_id,
        config=config,
        fetcher=fetcher,
    ))

    paths_03 = StagePaths.for_stage(run_dir, "03", "candidate_urls")
    _record_and_check(run_score_candidate_urls(
        input_path=paths_02.output_path,
        stage_paths=paths_03,
        run_id=run_id,
        config=config,
    ))

    paths_04 = StagePaths.for_stage(run_dir, "04", "markdown_pages")
    _record_and_check(run_generate_markdown_pages(
        input_path=paths_03.output_path,
        stage_paths=paths_04,
        run_id=run_id,
        config=config,
        fetcher=fetcher,
    ))

    return run_dir
