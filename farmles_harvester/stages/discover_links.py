from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from farmles_harvester.models.record_contracts import (
    VALIDATED_SOURCE_REQUIRED,
    missing_fields,
)
from farmles_harvester.pipeline.jsonl import JsonlWriter, stream_jsonl, write_json
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.stages.score_candidate_urls import LinkRecord, score_discovered_link
from farmles_harvester.web.html_utils import extract_links_from_html
from farmles_harvester.web.url_utils import is_internal_link, normalize_url

_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


def _is_processable(record: dict) -> bool:
    if record.get("validation_status") not in ("valid", "redirected"):
        return False
    if not record.get("final_url"):
        return False
    ct = record.get("content_type")
    if not ct:
        return False
    ct_lower = ct.lower()
    return any(ct_lower.startswith(t) for t in _HTML_CONTENT_TYPES)


def run_discover_links(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
    fetcher=None,
) -> StageResult:
    started_at = datetime.now(timezone.utc).isoformat()
    cfg = config or {}
    max_depth = cfg.get("max_depth", 1)
    follow_threshold = cfg.get("follow_threshold", 40)

    processed_sources = 0
    skipped_sources = 0
    source_fetch_errors = 0
    internal_links = 0
    external_links = 0
    max_depth_reached = 0
    input_count = 0
    output_count = 0
    error_count = 0

    queue: deque = deque()
    visited: set[str] = set()

    # Seed the BFS queue from validated input records
    input_records_for_queue: list[tuple[str, str, str]] = []
    for record in stream_jsonl(input_path):
        input_count += 1
        missing = missing_fields(record, VALIDATED_SOURCE_REQUIRED)
        if missing:
            input_records_for_queue.append(("error", record, missing))
        elif not _is_processable(record):
            skipped_sources += 1
        else:
            final_url = record["final_url"]
            visited.add(final_url)
            queue.append((final_url, 1, record["source_lead_id"], final_url))

    with JsonlWriter(stage_paths.output_path) as out, \
         JsonlWriter(stage_paths.errors_path) as err:

        # Write validation errors collected during seed pass
        for kind, record, missing in input_records_for_queue:
            if kind == "error":
                err.write({
                    "run_id": run_id,
                    "stage_name": "discover_links",
                    "source_lead_id": record.get("source_lead_id"),
                    "source_url": record.get("final_url"),
                    "error_type": "invalid_input_record",
                    "message": f"Missing required fields: {sorted(missing)}",
                    "retryable": False,
                    "created_at": started_at,
                })
                error_count += 1

        while queue:
            fetch_url, current_depth, lead_id, seed_url = queue.popleft()
            if current_depth > max_depth_reached:
                max_depth_reached = current_depth

            discovered_at = datetime.now(timezone.utc).isoformat()

            try:
                response = fetcher.fetch(fetch_url)
                links = extract_links_from_html(response.text, base_url=fetch_url)
            except Exception as exc:
                source_fetch_errors += 1
                error_count += 1
                err.write({
                    "run_id": run_id,
                    "stage_name": "discover_links",
                    "source_lead_id": lead_id,
                    "source_url": fetch_url,
                    "error_type": "fetch_error",
                    "message": str(exc),
                    "retryable": True,
                    "created_at": started_at,
                })
                continue

            processed_sources += 1

            for link in links:
                norm = normalize_url(link.discovered_url)
                discovered_url = norm.normalized_url if norm.normalized_url else link.discovered_url

                internal = is_internal_link(fetch_url, discovered_url)
                if internal:
                    internal_links += 1
                else:
                    external_links += 1

                out.write({
                    "run_id": run_id,
                    "source_lead_id": lead_id,
                    "source_url": seed_url,
                    "raw_href": link.raw_href,
                    "discovered_url": discovered_url,
                    "link_text": link.link_text,
                    "is_internal": internal,
                    "follow_allowed": internal,
                    "source_domain": urlparse(seed_url).netloc,
                    "discovered_domain": urlparse(discovered_url).netloc,
                    "depth": current_depth,
                    "discovery_method": "html_anchor",
                    "discovered_at": discovered_at,
                })
                output_count += 1

                if internal and discovered_url not in visited and current_depth < max_depth:
                    visited.add(discovered_url)
                    link_rec = LinkRecord(
                        discovered_url=discovered_url,
                        link_text=link.link_text,
                        is_internal=True,
                        follow_allowed=True,
                    )
                    if score_discovered_link(link_rec, config=config).candidate_score >= follow_threshold:
                        queue.append((link.discovered_url, current_depth + 1, lead_id, seed_url))

    completed_at = datetime.now(timezone.utc).isoformat()

    counts = {
        "input_records": input_count,
        "processed_sources": processed_sources,
        "skipped_sources": skipped_sources,
        "source_fetch_errors": source_fetch_errors,
        "output_records": output_count,
        "internal_links": internal_links,
        "external_links": external_links,
        "error_records": error_count,
        "max_depth_reached": max_depth_reached,
    }

    summary = {
        "stage_name": "discover_links",
        "stage_number": "02",
        "run_id": run_id,
        **counts,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    write_json(stage_paths.summary_path, summary)

    return StageResult(
        stage_id="02_discover_links",
        stage_number="02",
        stage_name="discover_links",
        status=STAGE_STATUS_COMPLETED,
        consumed_artifacts=[input_path.name],
        produced_artifacts=[stage_paths.output_path.name],
        summary_artifact=stage_paths.summary_path.name,
        error_artifact=stage_paths.errors_path.name,
        counts=counts,
        started_at=started_at,
        completed_at=completed_at,
    )
