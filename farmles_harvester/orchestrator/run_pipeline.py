import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from farmles_harvester.constants import SourceRelevanceLabel
from farmles_harvester.orchestrator.exceptions import PipelineError
from farmles_harvester.orchestrator.manifest import (
    create_initial_manifest,
    record_stage_result,
    write_manifest,
)
from farmles_harvester.orchestrator.registry_ingest import (
    ingest_fetch_outcomes,
    ingest_markdown_outcomes,
    ingest_source_relevance,
    ingest_urls,
    ingest_validation_failures,
)
from farmles_harvester.orchestrator.run_dynamic_pipeline import run_dynamic_pipeline
from farmles_harvester.pipeline.jsonl import read_jsonl, stream_jsonl, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.registry.url_registry import UrlRegistry
from farmles_harvester.stages.discover_links import run_discover_links
from farmles_harvester.web.fetcher import HttpFetcher
from farmles_harvester.stages.generate_markdown_pages import run_generate_markdown_pages
from farmles_harvester.stages.normalize_source_leads import run_normalize_source_leads
from farmles_harvester.stages.score_candidate_urls import run_score_candidate_urls
from farmles_harvester.stages.score_source_relevance import run_score_source_relevance
from farmles_harvester.stages.strip_boilerplate_blocks import run_strip_boilerplate_blocks
from farmles_harvester.stages.validate_urls import run_validate_urls
from farmles_harvester.web.render_type_detector import detect_render_type
from farmles_harvester.web.url_utils import source_url_to_slug


def run_pipeline(
    seed_file: Path,
    tag: str,
    runs_dir: Path,
    config: dict | None = None,
    fetcher=None,
    on_stage_start: Callable[[str, str], None] | None = None,
    registry_db: Path | None = None,
) -> Path:
    if fetcher is None:
        fetcher = HttpFetcher()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    run_id = f"{timestamp}_{tag}"
    run_dir = runs_dir / run_id

    if run_dir.exists():
        raise FileExistsError(f"Run folder already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    seed_snapshot = run_dir / "seed_urls.txt"
    shutil.copy2(seed_file, seed_snapshot)

    registry_path = registry_db if registry_db is not None else run_dir / "url_registry.db"

    created_at = datetime.now(timezone.utc).isoformat()
    manifest = create_initial_manifest(
        run_id=run_id,
        tag=tag,
        seed_file_snapshot=str(seed_file),
        created_at=created_at,
    )
    manifest["registry_db"] = str(registry_path)
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

    registry = UrlRegistry(registry_path)
    try:
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

        _safe_ingest(
            "validation failures",
            lambda: ingest_validation_failures(registry, paths_01.output_path, run_id),
        )

        # Detect JS-rendered source URLs before link discovery. Such URLs produce
        # zero discovered links in stage 02 (HTTP fetch sees an empty SPA shell),
        # so they are silently dropped. Identifying them here lets them bypass stages
        # 02–05 and go directly to the dynamic pipeline (d01).
        direct_dynamic_seeds = _collect_direct_dynamic_seeds(
            validated_path=paths_01.output_path,
            run_dir=run_dir,
            run_id=run_id,
            fetcher=fetcher,
        )

        paths_02 = StagePaths.for_stage(run_dir, "02", "discovered_links")
        _notify("02_discover_links", "Crawling")
        _record_and_check(run_discover_links(
            input_path=paths_01.output_path,
            stage_paths=paths_02,
            run_id=run_id,
            config=config,
            fetcher=fetcher,
            registry=registry,
        ))

        paths_03 = StagePaths.for_stage(run_dir, "03", "candidate_urls")
        _notify("03_score_candidate_urls", "Scoring")
        _record_and_check(run_score_candidate_urls(
            input_path=paths_02.output_path,
            stage_paths=paths_03,
            run_id=run_id,
            config=config,
        ))
        _safe_ingest(
            "urls",
            lambda: ingest_urls(registry, paths_02.output_path, paths_03.output_path, run_id),
        )

        slug_to_source_url = _build_slug_map(paths_03.output_path)

        paths_04 = StagePaths.for_stage(run_dir, "04", "markdown_pages")
        _notify("04_generate_markdown_pages", "Generating pages")
        _record_and_check(run_generate_markdown_pages(
            input_path=paths_03.output_path,
            stage_paths=paths_04,
            run_id=run_id,
            config=config,
            fetcher=fetcher,
            registry=registry,
        ))
        _safe_ingest(
            "fetch outcomes",
            lambda: ingest_fetch_outcomes(
                registry, paths_04.output_path, paths_02.errors_path, run_id
            ),
        )
        _safe_ingest(
            "markdown outcomes",
            lambda: ingest_markdown_outcomes(registry, paths_04.output_path, run_id),
        )

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
        _safe_ingest(
            "source relevance",
            lambda: ingest_source_relevance(
                registry, paths_06.output_path, slug_to_source_url, run_id
            ),
        )
        _print_relevance_summary(paths_06.output_path)

        dynamic_candidates = [
            r for r in read_jsonl(paths_05.output_path)
            if r.get("render_type") == "dynamic_js"
        ]
        # Merge source URLs that were pre-identified as JS-rendered. They bypassed
        # stages 02–05, so they won't appear in paths_05 output. Deduplicate against
        # anything already discovered through the normal static pipeline.
        seen_dynamic_urls = {r["candidate_url"] for r in dynamic_candidates}
        for seed in direct_dynamic_seeds:
            if seed["candidate_url"] not in seen_dynamic_urls:
                dynamic_candidates.append(seed)
        dynamic_candidates_path = run_dir / "dynamic_candidates.jsonl"
        write_jsonl(dynamic_candidates_path, dynamic_candidates)
        _notify("d01_browser_fetched_pages", "Browser-fetching dynamic pages")
        dynamic_result = run_dynamic_pipeline(
            input_path=dynamic_candidates_path,
            run_dir=run_dir,
            registry=registry,
            run_id=run_id,
        )
        record_stage_result(manifest, dynamic_result)
        write_manifest(manifest_path, manifest)
    finally:
        registry.close()

    return run_dir


def _build_slug_map(candidate_path: Path) -> dict[str, str]:
    slug_to_source_url: dict[str, str] = {}
    if not candidate_path.exists():
        return slug_to_source_url
    for rec in stream_jsonl(candidate_path):
        source_url = rec.get("source_url")
        if not source_url:
            continue
        slug = source_url_to_slug(source_url)
        slug_to_source_url.setdefault(slug, source_url)
    return slug_to_source_url


def _safe_ingest(label: str, fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception as exc:
        print(f"[registry] warning: failed to ingest {label}: {exc}")


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


def _collect_direct_dynamic_seeds(
    validated_path: Path,
    run_dir: Path,
    run_id: str,
    fetcher,
) -> list[dict]:
    """Return candidate records for source URLs that are themselves JS-rendered.

    Stage 02 discovers links FROM each source URL via HTTP, but a JS-rendered source
    yields an empty SPA shell — no <a> tags, zero discovered links, and the source
    URL is silently dropped. This function detects such URLs after stage 01 validation
    and builds minimal candidate records so they can be injected directly into d01,
    bypassing stages 02–05.

    Each returned record contains the three fields Crawl4AIFetcher requires:
    candidate_url, source_slug, and markdown_path (absolute, under run_dir).
    """
    seeds: list[dict] = []
    for record in stream_jsonl(validated_path):
        if record.get("validation_status") not in ("valid", "redirected"):
            continue
        url = record.get("final_url")
        if not url:
            continue
        try:
            response = fetcher.fetch(url)
        except Exception as exc:
            print(f"[dynamic-seed] warning: could not fetch {url} for render-type check: {exc}")
            continue
        render_type, _ = detect_render_type(response.text)
        if render_type != "dynamic_js":
            continue
        source_slug = source_url_to_slug(url)
        parsed_path = urlparse(url).path.strip("/")
        rel = Path(parsed_path) / "index.md" if parsed_path else Path("index.md")
        md_path = run_dir / "generated_wiki" / "sources" / source_slug / rel
        seeds.append({
            "run_id": run_id,
            "candidate_url": url,
            "source_slug": source_slug,
            "markdown_path": str(md_path),
            "render_type": "dynamic_js",
        })
        print(f"[dynamic-seed] {url} classified as dynamic_js — will bypass static pipeline")
    return seeds
