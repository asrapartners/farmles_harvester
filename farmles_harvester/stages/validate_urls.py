from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from farmles_harvester.models.record_contracts import (
    NORMALIZED_SOURCE_LEAD_REQUIRED,
    missing_fields,
)
from farmles_harvester.pipeline.jsonl import read_jsonl, write_json, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult
from farmles_harvester.web.fetcher import FetchTimeoutError

_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

_STATUS_VALID = "valid"
_STATUS_REDIRECTED = "redirected"
_STATUS_BROKEN = "broken"
_STATUS_BLOCKED = "blocked"
_STATUS_NON_HTML = "non_html"
_STATUS_TIMEOUT = "timeout"
_STATUS_INVALID_URL = "invalid_url"
_STATUS_FETCH_ERROR = "fetch_error"


def _is_html(content_type: str) -> bool:
    ct = content_type.lower()
    return any(ct.startswith(t) for t in _HTML_CONTENT_TYPES)


def _classify_response(response, normalized_url: str) -> tuple[str, bool, list[str], str | None]:
    """Returns (validation_status, redirected, redirect_chain, failure_reason)."""
    final_url = response.final_url if response.final_url is not None else response.url
    redirect_chain = list(response.redirect_chain)
    redirected = final_url != normalized_url or len(redirect_chain) > 1

    code = response.status_code

    if code in (404, 410):
        return _STATUS_BROKEN, False, redirect_chain, f"http_{code}"
    if code in (401, 403):
        return _STATUS_BLOCKED, False, redirect_chain, f"http_{code}"
    if code == 200:
        if not _is_html(response.content_type):
            return _STATUS_NON_HTML, redirected, redirect_chain, None
        if redirected:
            return _STATUS_REDIRECTED, True, redirect_chain, None
        return _STATUS_VALID, False, redirect_chain, None
    return _STATUS_FETCH_ERROR, False, redirect_chain, f"unexpected_status_{code}"


def run_validate_urls(
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

    counts: dict[str, int] = {
        _STATUS_VALID: 0,
        _STATUS_REDIRECTED: 0,
        _STATUS_BROKEN: 0,
        _STATUS_BLOCKED: 0,
        _STATUS_NON_HTML: 0,
        _STATUS_TIMEOUT: 0,
        _STATUS_INVALID_URL: 0,
        _STATUS_FETCH_ERROR: 0,
    }

    for record in input_records:
        missing = missing_fields(record, NORMALIZED_SOURCE_LEAD_REQUIRED)
        if missing:
            error_records.append({
                "run_id": run_id,
                "stage_name": "validate_urls",
                "source_lead_id": record.get("source_lead_id"),
                "normalized_url": record.get("normalized_url"),
                "error_type": "invalid_input_record",
                "message": f"Missing required fields: {sorted(missing)}",
                "retryable": False,
                "created_at": started_at,
            })
            counts[_STATUS_INVALID_URL] += 1
            continue

        normalized_url = record["normalized_url"]
        validated_at = datetime.now(timezone.utc).isoformat()

        try:
            response = fetcher.fetch(normalized_url)
            status, redirected, redirect_chain, failure_reason = _classify_response(response, normalized_url)
            final_url = response.final_url if response.final_url is not None else response.url
            output_records.append({
                "run_id": run_id,
                "source_lead_id": record["source_lead_id"],
                "input_url": record.get("input_url", ""),
                "normalized_url": normalized_url,
                "final_url": final_url,
                "domain": urlparse(normalized_url).netloc,
                "validation_status": status,
                "http_status": response.status_code,
                "content_type": response.content_type,
                "redirected": redirected,
                "redirect_chain": redirect_chain,
                "failure_reason": failure_reason,
                "validated_at": validated_at,
            })
        except FetchTimeoutError:
            status = _STATUS_TIMEOUT
            output_records.append({
                "run_id": run_id,
                "source_lead_id": record["source_lead_id"],
                "input_url": record.get("input_url", ""),
                "normalized_url": normalized_url,
                "final_url": normalized_url,
                "domain": urlparse(normalized_url).netloc,
                "validation_status": status,
                "http_status": None,
                "content_type": None,
                "redirected": False,
                "redirect_chain": [],
                "failure_reason": "timeout",
                "validated_at": validated_at,
            })
        except Exception as exc:
            status = _STATUS_FETCH_ERROR
            output_records.append({
                "run_id": run_id,
                "source_lead_id": record["source_lead_id"],
                "input_url": record.get("input_url", ""),
                "normalized_url": normalized_url,
                "final_url": normalized_url,
                "domain": urlparse(normalized_url).netloc,
                "validation_status": status,
                "http_status": None,
                "content_type": None,
                "redirected": False,
                "redirect_chain": [],
                "failure_reason": str(exc),
                "validated_at": validated_at,
            })

        counts[status] += 1

    write_jsonl(stage_paths.output_path, output_records)
    write_jsonl(stage_paths.errors_path, error_records)

    completed_at = datetime.now(timezone.utc).isoformat()

    summary = {
        "stage_name": "validate_urls",
        "stage_number": "01",
        "run_id": run_id,
        "input_records": len(input_records),
        "output_records": len(output_records),
        "error_records": len(error_records),
        "valid_count": counts[_STATUS_VALID],
        "redirected_count": counts[_STATUS_REDIRECTED],
        "broken_count": counts[_STATUS_BROKEN],
        "blocked_count": counts[_STATUS_BLOCKED],
        "non_html_count": counts[_STATUS_NON_HTML],
        "timeout_count": counts[_STATUS_TIMEOUT],
        "invalid_url_count": counts[_STATUS_INVALID_URL],
        "fetch_error_count": counts[_STATUS_FETCH_ERROR],
        "started_at": started_at,
        "completed_at": completed_at,
    }
    write_json(stage_paths.summary_path, summary)

    stage_counts = {k: v for k, v in summary.items() if k not in ("stage_name", "stage_number", "run_id", "started_at", "completed_at")}

    return StageResult(
        stage_id="01_validate_urls",
        stage_number="01",
        stage_name="validate_urls",
        status=STAGE_STATUS_COMPLETED,
        consumed_artifacts=[input_path.name],
        produced_artifacts=[stage_paths.output_path.name],
        summary_artifact=stage_paths.summary_path.name,
        error_artifact=stage_paths.errors_path.name,
        counts=stage_counts,
        started_at=started_at,
        completed_at=completed_at,
    )
