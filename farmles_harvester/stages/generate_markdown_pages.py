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
from farmles_harvester.registry.evaluation import evaluate_markdown_strength, rate_markdown_strength
from farmles_harvester.web.fetcher import FetchTimeoutError
from farmles_harvester.web.html_cleaner import clean_html
from farmles_harvester.web.render_type_detector import detect_render_type
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
    registry=None,
) -> StageResult:
    """Stage 04: fetch selected candidate pages and convert them to markdown wiki files.

    Reads 03_candidate_urls.jsonl, fetches each selected page via `fetcher`,
    cleans HTML, converts to markdown, and writes per-source wiki directories under
    generated_wiki/. Also writes:
      - 04_generated_pages.jsonl  (one record per processed page)
      - 04_generated_pages_errors.jsonl  (unexpected stage-level failures)
      - 04_generated_pages_summary.json
    Returns a StageResult with per-outcome counts.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    wiki_dir = stage_paths.output_path.parent / "generated_wiki"
    cfg = config or {}
    verbose_metadata = cfg.get("verbose_metadata", False)
    fast_mode = cfg.get("fast_mode", False) and registry is not None
    fast_md_min_words = cfg.get("fast_md_min_words", 150)
    fast_skip_permanent_failures = cfg.get("fast_skip_permanent_failures", True)

    # --- Phase 1: collect valid, selected, deduplicated records ---
    all_records = list(stream_jsonl(input_path))
    input_count = len(all_records)

    invalid_records: list[dict] = []
    skipped_candidates = 0
    fast_skipped = 0
    selected_records: list[dict] = []
    seen_urls: set[str] = set()
    source_candidates: dict[str, list[dict]] = {}
    seen_per_slug: dict[str, set[str]] = {}

    for record in all_records:
        missing = missing_fields(record, CANDIDATE_URL_REQUIRED)
        if missing:
            invalid_records.append(record)
            continue
        slug = source_url_to_slug(record["source_url"])
        url = record["candidate_url"]
        status = record["candidate_status"]
        include_in_pages = (status == CandidateStatus.SELECTED) or verbose_metadata
        if include_in_pages and url not in seen_per_slug.get(slug, set()):
            seen_per_slug.setdefault(slug, set()).add(url)
            source_candidates.setdefault(slug, []).append(record)
        if status != CandidateStatus.SELECTED:
            skipped_candidates += 1
            continue
        if url in seen_urls:
            skipped_candidates += 1
            continue
        seen_urls.add(url)
        selected_records.append(record)

    if fast_mode and selected_records:
        known = registry.get_many([r["candidate_url"] for r in selected_records])
        kept: list[dict] = []
        for record in selected_records:
            verdict = evaluate_markdown_strength(
                known.get(record["candidate_url"]),
                min_word_count=fast_md_min_words,
                skip_permanent_failures=fast_skip_permanent_failures,
            )
            if verdict.should_process:
                kept.append(record)
            else:
                fast_skipped += 1
        selected_records = kept

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
    fetched_paths: dict[str, str | None] = {}

    with JsonlWriter(stage_paths.output_path) as out, \
         JsonlWriter(stage_paths.errors_path) as err:

        for record in invalid_records:
            missing = missing_fields(record, CANDIDATE_URL_REQUIRED)
            err.write({
                "run_id": run_id,
                "stage_name": "generate_markdown_pages",
                "candidate_url": record.get("candidate_url"),
                "error_type": "invalid_input_record",
                "message": f"Missing required fields: {sorted(missing)}",
                "retryable": False,
                "created_at": started_at,
            })

        for record in selected_records:
            url = record["candidate_url"]
            generated_at = datetime.now(timezone.utc).isoformat()

            source_slug = source_url_to_slug(record["source_url"])
            source_dir = wiki_dir / "sources" / source_slug
            if source_slug not in source_folders_seen:
                source_folders_seen.add(source_slug)
            if source_slug not in source_metadata_written:
                source_metadata_written.add(source_slug)
                source_dir.mkdir(parents=True, exist_ok=True)

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
                fetched_paths[url] = None
                out.write({
                    "run_id": run_id,
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
                    "source_slug": source_slug,
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
                fetched_paths[url] = None
                non_html_count += 1
                out.write({
                    "run_id": run_id,
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

            render_type, _render_evidence = detect_render_type(response.text)

            min_retention = cfg.get("html_clean_min_word_retention", 0.15)
            html, content_retention = clean_html(response.text, min_word_retention=min_retention)

            rel_path = candidate_url_to_rel_path(url)
            md_path = source_dir / rel_path
            markdown_text = html_to_markdown(html, url)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(markdown_text, encoding="utf-8")
            markdown_files_written += 1
            pages_fetched += 1

            rel_path_str = f"generated_wiki/sources/{source_slug}/{rel_path}"
            fetched_paths[url] = str(rel_path)
            word_count = len(markdown_text.split())
            md_strong_min = cfg.get("md_strong_min_words", 300)
            md_medium_min = cfg.get("md_medium_min_words", 100)
            out.write({
                "run_id": run_id,
                "source_slug": source_slug,
                "candidate_url": url,
                "candidate_type": record["candidate_type"],
                "candidate_score": record.get("candidate_score"),
                "fetch_status": "fetched",
                "http_status": response.status_code,
                "content_type": response.content_type,
                "markdown_path": rel_path_str,
                "markdown_filename": rel_path.name,
                "render_type": render_type,
                "markdown_strength": rate_markdown_strength(word_count, strong_min=md_strong_min, medium_min=md_medium_min),
                "markdown_word_count": word_count,
                "content_hash": compute_content_hash(markdown_text),
                "content_retention_ratio": round(content_retention, 4),
                "generated_at": generated_at,
            })
            output_count += 1

    # --- Write source_metadata.json for each source after all fetching is done ---
    for slug in source_metadata_written:
        source_dir = wiki_dir / "sources" / slug
        first = source_candidates[slug][0]
        pages = [
            {
                "url": r["candidate_url"],
                "link_text": r.get("link_text"),
                "candidate_type": r["candidate_type"],
                "candidate_status": r["candidate_status"],
                "candidate_score": r.get("candidate_score"),
                "markdown_path": fetched_paths.get(r["candidate_url"]),
            }
            for r in source_candidates[slug]
        ]
        meta = {
            "source_slug": slug,
            "input_url": first.get("input_url"),
            "normalized_url": first.get("normalized_url"),
            "final_url": first.get("source_url"),
            "pages": pages,
        }
        (source_dir / "source_metadata.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

    completed_at = datetime.now(timezone.utc).isoformat()

    counts = {
        "input_records": input_count,
        "selected_candidates": selected_candidates,
        "skipped_candidates": skipped_candidates,
        "fast_skipped": fast_skipped,
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
