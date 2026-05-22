import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from markdownify import markdownify as md

from farmles_harvester.constants import CandidateStatus, CandidateType
from farmles_harvester.models.record_contracts import CANDIDATE_URL_REQUIRED, missing_fields
from farmles_harvester.pipeline.jsonl import read_jsonl, write_json, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.web.fetcher import FetchTimeoutError
from farmles_harvester.web.url_utils import source_url_to_slug

_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

_TYPE_TO_FILENAME: dict[str, str] = {
    CandidateType.GENERAL_MARKET_PAGE: "index.md",
    CandidateType.VENDOR_PAGE: "vendors.md",
    CandidateType.HOURS_LOCATION_PAGE: "visit.md",
    CandidateType.CALENDAR_EVENTS_PAGE: "events.md",
    CandidateType.ABOUT_CONTACT_PAGE: "about.md",
}


def candidate_type_to_filename(candidate_type: str) -> str:
    return _TYPE_TO_FILENAME.get(candidate_type, "page.md")


def normalize_markdown(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]

    cleaned_lines: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = not line.strip()

        if is_blank and previous_blank:
            continue

        cleaned_lines.append(line)
        previous_blank = is_blank

    return "\n".join(cleaned_lines).strip()


def html_to_markdown(html: str, source_url: str) -> str:
    if not source_url:
        raise ValueError("source_url must not be empty")

    markdown = md(html, heading_style="ATX")
    markdown = normalize_markdown(markdown)

    return f"{markdown}\n\n---\n\nSource: {source_url}\n"


def compute_content_hash(markdown_text: str) -> str:
    digest = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _resolve_filename(used: dict[str, set[str]], lead_id: str, base: str) -> str:
    if lead_id not in used:
        used[lead_id] = set()
    if base not in used[lead_id]:
        used[lead_id].add(base)
        return base
    stem, ext = base.rsplit(".", 1)
    n = 2
    while True:
        candidate = f"{stem}-{n}.{ext}"
        if candidate not in used[lead_id]:
            used[lead_id].add(candidate)
            return candidate
        n += 1


def _is_html(content_type: str | None) -> bool:
    if not content_type:
        return False
    ct = content_type.lower()
    return any(ct.startswith(t) for t in _HTML_CONTENT_TYPES)


def run_generate_markdown_pages(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
    fetcher=None,
) -> StageResult:
    started_at = datetime.now(timezone.utc).isoformat()
    wiki_dir = stage_paths.output_path.parent / "generated_wiki"

    input_records = read_jsonl(input_path)
    output_records: list[dict] = []
    error_records: list[dict] = []

    selected_candidates = 0
    skipped_candidates = 0
    pages_fetched = 0
    pages_failed = 0
    non_html_count = 0
    markdown_files_written = 0
    source_folders_seen: set[str] = set()
    used_filenames: dict[str, set[str]] = {}
    source_metadata_written: set[str] = set()

    for record in input_records:
        missing = missing_fields(record, CANDIDATE_URL_REQUIRED)
        if missing:
            error_records.append({
                "run_id": run_id,
                "stage_name": "generate_markdown_pages",
                "source_lead_id": record.get("source_lead_id"),
                "candidate_url": record.get("candidate_url"),
                "error_type": "invalid_input_record",
                "message": f"Missing required fields: {sorted(missing)}",
                "retryable": False,
                "created_at": started_at,
            })
            continue

        if record["candidate_status"] != CandidateStatus.SELECTED:
            skipped_candidates += 1
            continue

        selected_candidates += 1
        lead_id = record["source_lead_id"]
        candidate_url = record["candidate_url"]
        generated_at = datetime.now(timezone.utc).isoformat()

        source_slug = source_url_to_slug(record["source_url"])
        source_dir = wiki_dir / "sources" / source_slug
        pages_dir = source_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        if source_slug not in source_folders_seen:
            source_folders_seen.add(source_slug)
        if source_slug not in source_metadata_written:
            source_metadata_written.add(source_slug)
            meta = {
                "source_slug": source_slug,
                "input_url": None,
                "normalized_url": None,
                "final_url": record.get("source_url"),
            }
            (source_dir / "source_metadata.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )

        try:
            response = fetcher.fetch(candidate_url)
        except FetchTimeoutError as exc:
            output_records.append({
                "run_id": run_id,
                "source_lead_id": lead_id,
                "source_slug": source_slug,
                "candidate_url": candidate_url,
                "candidate_type": record["candidate_type"],
                "candidate_score": record.get("candidate_score"),
                "fetch_status": "timeout",
                "http_status": None,
                "content_type": None,
                "markdown_path": None,
                "markdown_filename": None,
                "content_hash": None,
                "generated_at": generated_at,
            })
            error_records.append({
                "run_id": run_id,
                "stage_name": "generate_markdown_pages",
                "source_lead_id": lead_id,
                "candidate_url": candidate_url,
                "error_type": "fetch_failed",
                "message": str(exc),
                "retryable": True,
                "created_at": started_at,
            })
            pages_failed += 1
            continue
        except Exception as exc:
            output_records.append({
                "run_id": run_id,
                "source_lead_id": lead_id,
                "source_slug": source_slug,
                "candidate_url": candidate_url,
                "candidate_type": record["candidate_type"],
                "candidate_score": record.get("candidate_score"),
                "fetch_status": "fetch_error",
                "http_status": None,
                "content_type": None,
                "markdown_path": None,
                "markdown_filename": None,
                "content_hash": None,
                "generated_at": generated_at,
            })
            error_records.append({
                "run_id": run_id,
                "stage_name": "generate_markdown_pages",
                "source_lead_id": lead_id,
                "candidate_url": candidate_url,
                "error_type": "fetch_failed",
                "message": str(exc),
                "retryable": True,
                "created_at": started_at,
            })
            pages_failed += 1
            continue

        if not _is_html(response.content_type):
            non_html_count += 1
            output_records.append({
                "run_id": run_id,
                "source_lead_id": lead_id,
                "source_slug": source_slug,
                "candidate_url": candidate_url,
                "candidate_type": record["candidate_type"],
                "candidate_score": record.get("candidate_score"),
                "fetch_status": "non_html",
                "http_status": response.status_code,
                "content_type": response.content_type,
                "markdown_path": None,
                "markdown_filename": None,
                "content_hash": None,
                "generated_at": generated_at,
            })
            continue

        base_filename = candidate_type_to_filename(record["candidate_type"])
        filename = _resolve_filename(used_filenames, source_slug, base_filename)
        markdown_text = html_to_markdown(response.text, candidate_url)

        md_path = pages_dir / filename
        md_path.write_text(markdown_text, encoding="utf-8")
        markdown_files_written += 1
        pages_fetched += 1

        rel_path = f"generated_wiki/sources/{source_slug}/pages/{filename}"
        output_records.append({
            "run_id": run_id,
            "source_lead_id": lead_id,
            "source_slug": source_slug,
            "candidate_url": candidate_url,
            "candidate_type": record["candidate_type"],
            "candidate_score": record.get("candidate_score"),
            "fetch_status": "fetched",
            "http_status": response.status_code,
            "content_type": response.content_type,
            "markdown_path": rel_path,
            "markdown_filename": filename,
            "content_hash": compute_content_hash(markdown_text),
            "generated_at": generated_at,
        })

    write_jsonl(stage_paths.output_path, output_records)
    write_jsonl(stage_paths.errors_path, error_records)

    completed_at = datetime.now(timezone.utc).isoformat()

    counts = {
        "input_records": len(input_records),
        "selected_candidates": selected_candidates,
        "skipped_candidates": skipped_candidates,
        "pages_fetched": pages_fetched,
        "pages_failed": pages_failed,
        "non_html_count": non_html_count,
        "markdown_files_written": markdown_files_written,
        "source_folders_created": len(source_folders_seen),
        "error_records": len(error_records),
    }

    summary = {
        "stage_name": "generate_markdown_pages",
        "stage_number": "04",
        "run_id": run_id,
        **counts,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    write_json(stage_paths.summary_path, summary)

    return StageResult(
        stage_id="04_generate_markdown_pages",
        stage_number="04",
        stage_name="generate_markdown_pages",
        status=STAGE_STATUS_COMPLETED,
        consumed_artifacts=[input_path.name],
        produced_artifacts=[stage_paths.output_path.name],
        summary_artifact=stage_paths.summary_path.name,
        error_artifact=stage_paths.errors_path.name,
        counts=counts,
        started_at=started_at,
        completed_at=completed_at,
    )
