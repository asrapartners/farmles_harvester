import json
from datetime import datetime, timezone
from pathlib import Path

from farmles_harvester.constants import SourceRelevanceLabel
from farmles_harvester.pipeline.jsonl import JsonlWriter, read_jsonl, write_json
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.wiki.relevance_scorer import score_source


def run_score_source_relevance(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
) -> StageResult:
    started_at = datetime.now(timezone.utc).isoformat()
    run_dir = stage_paths.output_path.parent

    all_records = read_jsonl(input_path)

    # Group MD file paths by source_slug
    source_paths: dict[str, list[Path]] = {}
    for record in all_records:
        if not record.get("markdown_path"):
            continue
        slug = record.get("source_slug", "")
        if not slug:
            continue
        abs_path = run_dir / record["markdown_path"]
        if abs_path.exists():
            source_paths.setdefault(slug, []).append(abs_path)

    counts_by_label: dict[str, int] = {
        SourceRelevanceLabel.CONFIRMED: 0,
        SourceRelevanceLabel.LIKELY: 0,
        SourceRelevanceLabel.UNCERTAIN: 0,
        SourceRelevanceLabel.LOW_CONFIDENCE: 0,
    }

    with JsonlWriter(stage_paths.output_path) as out, \
         JsonlWriter(stage_paths.errors_path) as _err:

        for slug, paths in source_paths.items():
            texts = [p.read_text(encoding="utf-8") for p in paths]
            result = score_source(texts, config=config)
            scored_at = datetime.now(timezone.utc).isoformat()

            label = result["relevance_label"]
            counts_by_label[label] = counts_by_label.get(label, 0) + 1

            record = {
                "run_id": run_id,
                "source_slug": slug,
                **result,
                "scored_at": scored_at,
            }
            out.write(record)

            # Patch source_metadata.json so the folder is self-describing
            meta_path = run_dir / "generated_wiki" / "sources" / slug / "source_metadata.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["relevance_label"] = label
                meta["relevance_score"] = result["relevance_score"]
                meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    completed_at = datetime.now(timezone.utc).isoformat()

    counts = {
        "total_sources": len(source_paths),
        "confirmed_count": counts_by_label[SourceRelevanceLabel.CONFIRMED],
        "likely_count": counts_by_label[SourceRelevanceLabel.LIKELY],
        "uncertain_count": counts_by_label[SourceRelevanceLabel.UNCERTAIN],
        "low_confidence_count": counts_by_label[SourceRelevanceLabel.LOW_CONFIDENCE],
    }

    summary = {
        "stage_name": "score_source_relevance",
        "stage_number": "06",
        "run_id": run_id,
        **counts,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    write_json(stage_paths.summary_path, summary)

    return StageResult(
        stage_id="06_score_source_relevance",
        stage_number="06",
        stage_name="score_source_relevance",
        status=STAGE_STATUS_COMPLETED,
        consumed_artifacts=[input_path.name],
        produced_artifacts=[stage_paths.output_path.name],
        summary_artifact=stage_paths.summary_path.name,
        error_artifact=stage_paths.errors_path.name,
        counts=counts,
        started_at=started_at,
        completed_at=completed_at,
    )
