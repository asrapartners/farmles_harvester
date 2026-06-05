from datetime import datetime, timezone
from pathlib import Path

from farmles_harvester.pipeline.jsonl import read_jsonl, write_json, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import (
    STAGE_STATUS_COMPLETED,
    STAGE_STATUS_SKIPPED,
    StageResult,
)
from farmles_harvester.registry.evaluation import rate_markdown_strength
from farmles_harvester.registry.url_registry import UrlRegistry
from farmles_harvester.web.crawl4ai_fetcher import Crawl4AIFetcher

_STAGE_NUMBER = "d01"
_ARTIFACT_NAME = "browser_fetched_pages"
_STAGE_ID = f"{_STAGE_NUMBER}_{_ARTIFACT_NAME}"


def run_dynamic_pipeline(
    input_path: Path,
    run_dir: Path,
    registry: UrlRegistry,
    run_id: str,
    max_concurrent: int = 5,
    use_cache: bool = False,
    fetcher: Crawl4AIFetcher | None = None,
) -> StageResult:
    """Fetch JS-rendered candidates via headless browser and write d01 artifacts."""
    started_at = datetime.now(timezone.utc).isoformat()
    stage_paths = StagePaths.for_stage(run_dir, _STAGE_NUMBER, _ARTIFACT_NAME)

    records = read_jsonl(input_path) if input_path.exists() else []
    if not records:
        return StageResult(
            stage_id=_STAGE_ID,
            stage_number=_STAGE_NUMBER,
            stage_name=_ARTIFACT_NAME,
            status=STAGE_STATUS_SKIPPED,
            consumed_artifacts=[str(input_path)],
            counts={"total": 0},
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    if fetcher is None:
        fetcher = Crawl4AIFetcher(max_concurrent=max_concurrent, use_cache=use_cache)

    try:
        ok_results, error_records = fetcher.fetch_batch(records)
    except Exception as exc:
        print(f"[dynamic] warning: fetch_batch raised unexpectedly: {exc}")
        ok_results = []
        error_records = [
            {"candidate_url": r["candidate_url"], "fetch_status": "fetch_error", "error": str(exc)}
            for r in records
        ]

    write_jsonl(stage_paths.output_path, ok_results)
    write_jsonl(stage_paths.errors_path, error_records)

    completed_at = datetime.now(timezone.utc).isoformat()

    thin_count = sum(1 for r in error_records if r.get("fetch_status") == "thin_content")
    summary = {
        "stage": _STAGE_ID,
        "total": len(records),
        "ok": len(ok_results),
        "thin_content": thin_count,
        "failed": len(error_records) - thin_count,
        "overwritten_count": sum(1 for r in ok_results if r.get("overwritten")),
        "total_bytes_before": sum(r.get("bytes_before", 0) for r in ok_results),
        "total_bytes_after": sum(r.get("bytes_after", 0) for r in ok_results),
        "started_at": started_at,
        "completed_at": completed_at,
    }
    write_json(stage_paths.summary_path, summary)

    for r in ok_results:
        _safe_record(registry, r, run_id)

    return StageResult(
        stage_id=_STAGE_ID,
        stage_number=_STAGE_NUMBER,
        stage_name=_ARTIFACT_NAME,
        status=STAGE_STATUS_COMPLETED,
        consumed_artifacts=[str(input_path)],
        produced_artifacts=[str(stage_paths.output_path)],
        summary_artifact=str(stage_paths.summary_path),
        error_artifact=str(stage_paths.errors_path),
        counts={
            "total": len(records),
            "ok": len(ok_results),
            "thin_content": thin_count,
            "failed": len(error_records) - thin_count,
            "overwritten": summary["overwritten_count"],
        },
        started_at=started_at,
        completed_at=completed_at,
    )


def _safe_record(registry: UrlRegistry, result: dict, run_id: str) -> None:
    try:
        registry.record_markdown_outcome(
            result["candidate_url"],
            status="generated",
            strength=rate_markdown_strength(result.get("word_count", 0)),
            word_count=result.get("word_count"),
            path=result.get("markdown_path"),
            run_id=run_id,
        )
    except Exception as exc:
        print(f"[registry] warning: failed to record markdown outcome for {result['candidate_url']}: {exc}")
