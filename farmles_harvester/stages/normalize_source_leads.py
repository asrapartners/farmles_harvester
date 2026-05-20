import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from farmles_harvester.pipeline.jsonl import write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import StageResult
from farmles_harvester.web.url_utils import normalize_url


@dataclass
class SourceLead:
    source_lead_id: str
    input_url: str
    normalized_url: str
    input_line: int
    normalization_notes: list[str]


def parse_seed_lines(seed_text: str) -> list[SourceLead]:
    leads: list[SourceLead] = []
    seen_urls: set[str] = set()
    lead_count = 0

    for line_num, line in enumerate(seed_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        result = normalize_url(stripped)
        if result.status != "normalized" or result.normalized_url is None:
            continue

        if result.normalized_url in seen_urls:
            continue

        seen_urls.add(result.normalized_url)
        lead_count += 1

        leads.append(SourceLead(
            source_lead_id=f"lead_{lead_count}",
            input_url=stripped,
            normalized_url=result.normalized_url,
            input_line=line_num,
            normalization_notes=result.notes,
        ))

    return leads


def run_normalize_source_leads(
    seed_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
) -> StageResult:
    started_at = datetime.now(timezone.utc).isoformat()

    seed_text = seed_path.read_text(encoding="utf-8")
    all_lines = seed_text.splitlines()

    blank_lines = sum(1 for l in all_lines if not l.strip())
    comment_lines = sum(1 for l in all_lines if l.strip().startswith("#"))
    candidate_lines = len(all_lines) - blank_lines - comment_lines

    leads = parse_seed_lines(seed_text)

    # Detect invalid URL lines for the errors artifact
    error_records: list[dict] = []
    for line_num, line in enumerate(all_lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        result = normalize_url(stripped)
        if result.status != "normalized":
            error_records.append({
                "run_id": run_id,
                "stage_name": "normalize_source_leads",
                "input_line": line_num,
                "input_url": stripped,
                "error_type": "invalid_url",
                "message": result.error_message,
                "retryable": False,
                "created_at": started_at,
            })

    duplicate_count = max(0, candidate_lines - len(error_records) - len(leads))

    normalized_at = datetime.now(timezone.utc).isoformat()
    output_records = [
        {
            "run_id": run_id,
            "source_lead_id": lead.source_lead_id,
            "input_url": lead.input_url,
            "normalized_url": lead.normalized_url,
            "input_line": lead.input_line,
            "normalization_status": "normalized",
            "normalization_notes": lead.normalization_notes,
            "normalized_at": normalized_at,
        }
        for lead in leads
    ]

    write_jsonl(stage_paths.output_path, output_records)
    write_jsonl(stage_paths.errors_path, error_records)

    completed_at = datetime.now(timezone.utc).isoformat()

    counts = {
        "total_input_lines": len(all_lines),
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "candidate_lines": candidate_lines,
        "output_records": len(output_records),
        "duplicate_count": duplicate_count,
        "invalid_url_count": len(error_records),
        "error_records": len(error_records),
    }

    summary = {
        "stage_name": "normalize_source_leads",
        "stage_number": "00",
        "run_id": run_id,
        **counts,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    stage_paths.summary_path.parent.mkdir(parents=True, exist_ok=True)
    stage_paths.summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return StageResult(
        stage_id="00_normalize_source_leads",
        stage_number="00",
        stage_name="normalize_source_leads",
        status="completed",
        consumed_artifacts=[seed_path.name],
        produced_artifacts=[stage_paths.output_path.name],
        summary_artifact=stage_paths.summary_path.name,
        error_artifact=stage_paths.errors_path.name,
        counts=counts,
        started_at=started_at,
        completed_at=completed_at,
    )
