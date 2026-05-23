import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from markdownify import markdownify as md

from farmles_harvester.constants import CandidateStatus
from farmles_harvester.models.record_contracts import CANDIDATE_URL_REQUIRED, missing_fields
from farmles_harvester.pipeline.jsonl import JsonlWriter, stream_jsonl, write_json
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.web.fetcher import FetchTimeoutError
from farmles_harvester.web.html_cleaner import (
    remove_low_density_blocks,
    remove_semantic_boilerplate,
)
from farmles_harvester.web.url_utils import source_url_to_slug

_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


def candidate_url_to_rel_path(candidate_url: str) -> Path:
    path = urlparse(candidate_url).path.strip("/")
    if not path:
        return Path("index.md")
    return Path(path) / "index.md"


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
    cfg = config or {}

    # --- Phase 1: collect valid, selected, deduplicated records ---
    all_records = list(stream_jsonl(input_path))
    input_count = len(all_records)

    invalid_records: list[dict] = []
    skipped_candidates = 0
    selected_records: list[dict] = []
    seen_urls: set[str] = set()

    for record in all_records:
        missing = missing_fields(record, CANDIDATE_URL_REQUIRED)
        if missing:
            invalid_records.append(record)
            continue
        if record["candidate_status"] != CandidateStatus.SELECTED:
            skipped_candidates += 1
            continue
        url = record["candidate_url"]
        if url in seen_urls:
            skipped_candidates += 1
            continue
        seen_urls.add(url)
        selected_records.append(record)

    selected_candidates = len(selected_records)
    error_count = len(invalid_records)

    # --- Phase 2: fetch, strip boilerplate, convert, write ---
    output_count = 0
    pages_fetched = 0
    pages_failed = 0
    non_html_count = 0
    markdown_files_written = 0
    source_folders_seen: set[str] = set()
    source_metadata_written: set[str] = set()

    with JsonlWriter(stage_paths.output_path) as out, \
         JsonlWriter(stage_paths.errors_path) as err:

        for record in invalid_records:
            missing = missing_fields(record, CANDIDATE_URL_REQUIRED)
            err.write({
                "run_id": run_id,
                "stage_name": "generate_markdown_pages",
                "source_lead_id": record.get("source_lead_id"),
                "candidate_url": record.get("candidate_url"),
                "error_type": "invalid_input_record",
                "message": f"Missing required fields: {sorted(missing)}",
                "retryable": False,
                "created_at": started_at,
            })

        for record in selected_records:
            url = record["candidate_url"]
            lead_id = record["source_lead_id"]
            generated_at = datetime.now(timezone.utc).isoformat()

            source_slug = source_url_to_slug(record["source_url"])
            source_dir = wiki_dir / "sources" / source_slug
            if source_slug not in source_folders_seen:
                source_folders_seen.add(source_slug)
            if source_slug not in source_metadata_written:
                source_metadata_written.add(source_slug)
                source_dir.mkdir(parents=True, exist_ok=True)
                meta = {
                    "source_slug": source_slug,
                    "input_url": None,
                    "normalized_url": None,
                    "final_url": record.get("source_url"),
                }
                (source_dir / "source_metadata.json").write_text(
                    json.dumps(meta, indent=2), encoding="utf-8"
                )

            response = None
            error_type = None
            exc = None
            try:
                response = fetcher.fetch(url)
            except FetchTimeoutError as e:
                error_type, exc = "timeout", e
            except Exception as e:
                error_type, exc = "fetch_error", e

            if error_type:
                out.write({
                    "run_id": run_id,
                    "source_lead_id": lead_id,
                    "source_slug": source_slug,
                    "candidate_url": url,
                    "candidate_type": record["candidate_type"],
                    "candidate_score": record.get("candidate_score"),
                    "fetch_status": error_type,
                    "http_status": None,
                    "content_type": None,
                    "markdown_path": None,
                    "markdown_filename": None,
                    "content_hash": None,
                    "generated_at": generated_at,
                })
                output_count += 1
                err.write({
                    "run_id": run_id,
                    "stage_name": "generate_markdown_pages",
                    "source_lead_id": lead_id,
                    "candidate_url": url,
                    "error_type": "fetch_failed",
                    "message": str(exc),
                    "retryable": True,
                    "created_at": started_at,
                })
                error_count += 1
                pages_failed += 1
                continue

            if not _is_html(response.content_type):
                non_html_count += 1
                out.write({
                    "run_id": run_id,
                    "source_lead_id": lead_id,
                    "source_slug": source_slug,
                    "candidate_url": url,
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
                output_count += 1
                continue

            html = remove_semantic_boilerplate(response.text)
            html = remove_low_density_blocks(html)

            rel_path = candidate_url_to_rel_path(url)
            md_path = source_dir / rel_path
            markdown_text = html_to_markdown(html, url)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(markdown_text, encoding="utf-8")
            markdown_files_written += 1
            pages_fetched += 1

            rel_path_str = f"generated_wiki/sources/{source_slug}/{rel_path}"
            out.write({
                "run_id": run_id,
                "source_lead_id": lead_id,
                "source_slug": source_slug,
                "candidate_url": url,
                "candidate_type": record["candidate_type"],
                "candidate_score": record.get("candidate_score"),
                "fetch_status": "fetched",
                "http_status": response.status_code,
                "content_type": response.content_type,
                "markdown_path": rel_path_str,
                "markdown_filename": rel_path.name,
                "content_hash": compute_content_hash(markdown_text),
                "generated_at": generated_at,
            })
            output_count += 1

    completed_at = datetime.now(timezone.utc).isoformat()

    counts = {
        "input_records": input_count,
        "selected_candidates": selected_candidates,
        "skipped_candidates": skipped_candidates,
        "pages_fetched": pages_fetched,
        "pages_failed": pages_failed,
        "non_html_count": non_html_count,
        "markdown_files_written": markdown_files_written,
        "source_folders_created": len(source_folders_seen),
        "error_records": error_count,
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
