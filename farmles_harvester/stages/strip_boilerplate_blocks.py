import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from farmles_harvester.pipeline.jsonl import JsonlWriter, read_jsonl, write_json
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.wiki.markdown_cleaner import build_md_fingerprint, strip_md_fingerprint


def run_strip_boilerplate_blocks(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
) -> StageResult:
    started_at = datetime.now(timezone.utc).isoformat()
    cfg = config or {}
    threshold = cfg.get("boilerplate_threshold", 0.8)
    min_files = cfg.get("min_files_for_fingerprint", 3)
    run_dir = stage_paths.output_path.parent

    # Group fetched markdown paths by source_slug
    all_records = read_jsonl(input_path)
    source_paths: dict[str, list[tuple[dict, Path]]] = {}
    for record in all_records:
        if record.get("fetch_status") != "fetched" or not record.get("markdown_path"):
            continue
        slug = record["source_slug"]
        abs_path = run_dir / record["markdown_path"]
        if not abs_path.exists():
            continue
        source_paths.setdefault(slug, []).append((record, abs_path))

    sources_processed = 0
    files_modified = 0
    total_blocks_removed = 0

    with JsonlWriter(stage_paths.output_path) as out, \
         JsonlWriter(stage_paths.errors_path) as err:

        for slug, file_entries in source_paths.items():
            sources_processed += 1
            contents = [path.read_text(encoding="utf-8") for _, path in file_entries]
            fingerprint = build_md_fingerprint(contents, threshold=threshold, min_files=min_files)

            for record, path in file_entries:
                original = path.read_text(encoding="utf-8")
                cleaned = strip_md_fingerprint(original, fingerprint)

                original_blocks = [b for b in re.split(r"\n{2,}", original) if b.strip()]
                cleaned_blocks  = [b for b in re.split(r"\n{2,}", cleaned)  if b.strip()]
                blocks_removed = max(0, len(original_blocks) - len(cleaned_blocks))
                modified = cleaned != original.strip()

                if modified:
                    path.write_text(cleaned, encoding="utf-8")
                    files_modified += 1
                    total_blocks_removed += blocks_removed

                content_hash = "sha256:" + hashlib.sha256(
                    (cleaned if modified else original).encode()
                ).hexdigest()

                out.write({
                    "run_id": run_id,
                    "source_slug": slug,
                    "markdown_path": record["markdown_path"],
                    "blocks_removed": blocks_removed,
                    "content_hash": content_hash,
                    "modified": modified,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                })

    completed_at = datetime.now(timezone.utc).isoformat()
    counts = {
        "sources_processed": sources_processed,
        "files_modified": files_modified,
        "total_blocks_removed": total_blocks_removed,
        "total_files": sum(len(v) for v in source_paths.values()),
    }
    summary = {
        "stage_name": "strip_boilerplate_blocks",
        "stage_number": "05",
        "run_id": run_id,
        **counts,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    write_json(stage_paths.summary_path, summary)

    return StageResult(
        stage_id="05_strip_boilerplate_blocks",
        stage_number="05",
        stage_name="strip_boilerplate_blocks",
        status=STAGE_STATUS_COMPLETED,
        consumed_artifacts=[input_path.name],
        produced_artifacts=[stage_paths.output_path.name],
        summary_artifact=stage_paths.summary_path.name,
        error_artifact=stage_paths.errors_path.name,
        counts=counts,
        started_at=started_at,
        completed_at=completed_at,
    )
