import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from farmles_harvester.constants import SourceRelevanceLabel
from farmles_harvester.orchestrator.exceptions import PipelineError
from farmles_harvester.orchestrator.manifest import (
    create_initial_manifest,
    record_stage_result,
    write_manifest,
)
from farmles_harvester.pipeline.jsonl import read_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.stages.discover_links import run_discover_links
from farmles_harvester.stages.generate_markdown_pages import run_generate_markdown_pages
from farmles_harvester.stages.normalize_source_leads import run_normalize_source_leads
from farmles_harvester.stages.score_candidate_urls import run_score_candidate_urls
from farmles_harvester.stages.score_source_relevance import run_score_source_relevance
from farmles_harvester.stages.strip_boilerplate_blocks import run_strip_boilerplate_blocks
from farmles_harvester.stages.validate_urls import run_validate_urls


def run_pipeline(
    seed_file: Path,
    tag: str,
    runs_dir: Path,
    config: dict | None = None,
    fetcher=None,
    on_stage_start: Callable[[str, str], None] | None = None,
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
        seed_file_snapshot=str(seed_file),
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

    def _notify(stage_id: str, label: str) -> None:
        if on_stage_start:
            on_stage_start(stage_id, label)

    paths_00 = StagePaths.for_stage(run_dir, "00", "normalized_source_leads")
    _notify("00_normalize_source_leads", "Normalising seeds")
    _record_and_check(run_normalize_source_leads(
        input_path=seed_snapshot,
        stage_paths=paths_00,
        run_id=run_id,
        config=config,
    ))

    paths_01 = StagePaths.for_stage(run_dir, "01", "validated_sources")
    _notify("01_validate_urls", "Validating")
    _record_and_check(run_validate_urls(
        input_path=paths_00.output_path,
        stage_paths=paths_01,
        run_id=run_id,
        config=config,
        fetcher=fetcher,
    ))

    paths_02 = StagePaths.for_stage(run_dir, "02", "discovered_links")
    _notify("02_discover_links", "Crawling")
    _record_and_check(run_discover_links(
        input_path=paths_01.output_path,
        stage_paths=paths_02,
        run_id=run_id,
        config=config,
        fetcher=fetcher,
    ))

    paths_03 = StagePaths.for_stage(run_dir, "03", "candidate_urls")
    _notify("03_score_candidate_urls", "Scoring")
    _record_and_check(run_score_candidate_urls(
        input_path=paths_02.output_path,
        stage_paths=paths_03,
        run_id=run_id,
        config=config,
    ))

    paths_04 = StagePaths.for_stage(run_dir, "04", "markdown_pages")
    _notify("04_generate_markdown_pages", "Generating pages")
    _record_and_check(run_generate_markdown_pages(
        input_path=paths_03.output_path,
        stage_paths=paths_04,
        run_id=run_id,
        config=config,
        fetcher=fetcher,
    ))

    paths_05 = StagePaths.for_stage(run_dir, "05", "stripped_pages")
    _notify("05_strip_boilerplate_blocks", "Stripping boilerplate")
    _record_and_check(run_strip_boilerplate_blocks(
        input_path=paths_04.output_path,
        stage_paths=paths_05,
        run_id=run_id,
        config=config,
    ))

    paths_06 = StagePaths.for_stage(run_dir, "06", "source_relevance")
    _notify("06_score_source_relevance", "Scoring source relevance")
    result_06 = run_score_source_relevance(
        input_path=paths_05.output_path,
        stage_paths=paths_06,
        run_id=run_id,
        config=config,
    )
    _record_and_check(result_06)
    _print_relevance_summary(paths_06.output_path)

    return run_dir


def _print_relevance_summary(relevance_jsonl: Path) -> None:
    if not relevance_jsonl.exists():
        return

    records = read_jsonl(relevance_jsonl)
    counts: dict[str, int] = {}
    low_conf: list[dict] = []

    for r in records:
        label = r.get("relevance_label", "unknown")
        counts[label] = counts.get(label, 0) + 1
        if label == SourceRelevanceLabel.LOW_CONFIDENCE:
            low_conf.append(r)

    print()
    print("── Source Relevance Summary ──────────────────────────────────")
    for label in [
        SourceRelevanceLabel.CONFIRMED,
        SourceRelevanceLabel.LIKELY,
        SourceRelevanceLabel.UNCERTAIN,
        SourceRelevanceLabel.LOW_CONFIDENCE,
    ]:
        n = counts.get(label, 0)
        note = "  ← review before next run" if label == SourceRelevanceLabel.LOW_CONFIDENCE and n else ""
        print(f"  {label:<20} {n}{note}")

    if low_conf:
        print()
        print("  Low-confidence sources:")
        for r in sorted(low_conf, key=lambda x: x["source_slug"]):
            hits = r.get("keyword_hits", 0)
            words = r.get("total_word_count", 0)
            print(f"    • {r['source_slug']:<50}  ({hits} keyword hits, {words} words)")
    print("─────────────────────────────────────────────────────────────")
