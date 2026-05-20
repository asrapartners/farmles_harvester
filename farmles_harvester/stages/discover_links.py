from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from farmles_harvester.models.record_contracts import (
    VALIDATED_SOURCE_REQUIRED,
    missing_fields,
)
from farmles_harvester.pipeline.jsonl import read_jsonl, write_json, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.web.html_utils import extract_links_from_html
from farmles_harvester.web.url_utils import is_internal_link

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

    input_records = read_jsonl(input_path)
    output_records: list[dict] = []
    error_records: list[dict] = []

    processed_sources = 0
    skipped_sources = 0
    source_fetch_errors = 0
    internal_links = 0
    external_links = 0

    for record in input_records:
        missing = missing_fields(record, VALIDATED_SOURCE_REQUIRED)
        if missing:
            error_records.append({
                "run_id": run_id,
                "stage_name": "discover_links",
                "source_lead_id": record.get("source_lead_id"),
                "source_url": record.get("final_url"),
                "error_type": "invalid_input_record",
                "message": f"Missing required fields: {sorted(missing)}",
                "retryable": False,
                "created_at": started_at,
            })
            continue

        if not _is_processable(record):
            skipped_sources += 1
            continue

        final_url = record["final_url"]
        discovered_at = datetime.now(timezone.utc).isoformat()

        try:
            response = fetcher.fetch(final_url)
            links = extract_links_from_html(response.text, base_url=final_url)
        except Exception as exc:
            source_fetch_errors += 1
            error_records.append({
                "run_id": run_id,
                "stage_name": "discover_links",
                "source_lead_id": record["source_lead_id"],
                "source_url": final_url,
                "error_type": "fetch_error",
                "message": str(exc),
                "retryable": True,
                "created_at": started_at,
            })
            continue

        processed_sources += 1

        for link in links:
            internal = is_internal_link(final_url, link.discovered_url)
            if internal:
                internal_links += 1
            else:
                external_links += 1

            output_records.append({
                "run_id": run_id,
                "source_lead_id": record["source_lead_id"],
                "source_url": final_url,
                "raw_href": link.raw_href,
                "discovered_url": link.discovered_url,
                "link_text": link.link_text,
                "is_internal": internal,
                "follow_allowed": internal,
                "source_domain": urlparse(final_url).netloc,
                "discovered_domain": urlparse(link.discovered_url).netloc,
                "depth": 1,
                "discovery_method": "html_anchor",
                "discovered_at": discovered_at,
            })

    write_jsonl(stage_paths.output_path, output_records)
    write_jsonl(stage_paths.errors_path, error_records)

    completed_at = datetime.now(timezone.utc).isoformat()

    counts = {
        "input_records": len(input_records),
        "processed_sources": processed_sources,
        "skipped_sources": skipped_sources,
        "source_fetch_errors": source_fetch_errors,
        "output_records": len(output_records),
        "internal_links": internal_links,
        "external_links": external_links,
        "error_records": len(error_records),
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
