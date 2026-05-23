import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from farmles_harvester.constants import CandidateType, CandidateStatus, CandidateStrength
from farmles_harvester.models.record_contracts import DISCOVERED_LINK_REQUIRED, missing_fields
from farmles_harvester.pipeline.jsonl import JsonlWriter, stream_jsonl, write_json
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult

_POSITIVE_SIGNAL_GROUPS: list[tuple[frozenset[str], str, int]] = [
    (frozenset({"vendor", "vendors", "our-vendors"}), CandidateType.VENDOR_PAGE, 50),
    (frozenset({"hours", "schedule", "season", "open"}), CandidateType.HOURS_LOCATION_PAGE, 40),
    (frozenset({"visit", "location", "directions", "parking", "map"}), CandidateType.HOURS_LOCATION_PAGE, 40),
    (frozenset({"calendar", "events", "opening-day"}), CandidateType.CALENDAR_EVENTS_PAGE, 40),
    (frozenset({"about", "contact", "faq"}), CandidateType.ABOUT_CONTACT_PAGE, 35),
    (frozenset({"market", "farmers-market"}), CandidateType.GENERAL_MARKET_PAGE, 30),
]

_HARD_REJECT = frozenset({"privacy", "terms", "cookies", "login", "cart", "checkout", "wp-admin"})
_SOFT_PENALTY = frozenset({"feed", "rss", "tag", "category", "author", "blog", "archive", "covid"})

_DEFAULT_SELECTED_THRESHOLD = 40
_DEFAULT_STRONG_THRESHOLD = 70


@dataclass
class LinkRecord:
    discovered_url: str
    link_text: str
    is_internal: bool
    follow_allowed: bool = True


@dataclass
class CandidateScore:
    candidate_score: int
    candidate_type: str
    candidate_status: str
    candidate_strength: str
    score_reasons: list[str]


def _tokenize(url: str, text: str) -> set[str]:
    path = urlparse(url).path.lower()
    raw_segments = {s for s in path.split("/") if s}
    word_tokens = {t for t in re.split(r"[/\-_]+", path) if t}
    text_tokens = set(text.lower().split())
    return raw_segments | word_tokens | text_tokens


def score_discovered_link(link_record: LinkRecord, config: dict | None = None) -> CandidateScore:
    cfg = config or {}
    selected_threshold = cfg.get("selected_threshold", _DEFAULT_SELECTED_THRESHOLD)
    strong_threshold = cfg.get("strong_candidate_threshold", _DEFAULT_STRONG_THRESHOLD)

    if not link_record.is_internal:
        return CandidateScore(
            candidate_score=0,
            candidate_type=CandidateType.EXTERNAL_REFERENCE,
            candidate_status=CandidateStatus.EXTERNAL_REFERENCE,
            candidate_strength=CandidateStrength.WEAK,
            score_reasons=["external link"],
        )

    tokens = _tokenize(link_record.discovered_url, link_record.link_text)
    score = 20
    reasons: list[str] = []
    candidate_type = CandidateType.UNKNOWN
    type_assigned = False
    hard_rejected = False

    # Pass 1: type (first match) + stacking score bonuses (all matches)
    for signal_set, ctype, points in _POSITIVE_SIGNAL_GROUPS:
        matched = signal_set & tokens
        if matched:
            score += points
            reasons.append(f"+{points} matched {sorted(matched)}")
            if not type_assigned:
                candidate_type = ctype
                type_assigned = True

    # Hard reject overrides type and penalises score
    hard_matched = _HARD_REJECT & tokens
    if hard_matched:
        score -= 60
        hard_rejected = True
        candidate_type = CandidateType.LOW_VALUE_PAGE
        reasons.append(f"-60 hard reject {sorted(hard_matched)}")

    # Soft penalties stack
    for term in _SOFT_PENALTY:
        if term in tokens:
            score -= 30
            reasons.append(f"-30 soft penalty: {term}")

    score = max(0, min(100, score))

    if hard_rejected:
        status = CandidateStatus.REJECTED
    elif score >= selected_threshold:
        status = CandidateStatus.SELECTED
    else:
        status = CandidateStatus.REJECTED

    if score >= strong_threshold:
        strength = CandidateStrength.STRONG
    elif score >= selected_threshold:
        strength = CandidateStrength.MEDIUM
    else:
        strength = CandidateStrength.WEAK

    return CandidateScore(
        candidate_score=score,
        candidate_type=candidate_type,
        candidate_status=status,
        candidate_strength=strength,
        score_reasons=reasons,
    )


def run_score_candidate_urls(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
) -> StageResult:
    started_at = datetime.now(timezone.utc).isoformat()

    input_count = 0
    output_count = 0
    error_count = 0
    selected_count = 0
    rejected_count = 0
    external_reference_count = 0
    strong_count = 0
    medium_count = 0
    weak_count = 0

    with JsonlWriter(stage_paths.output_path) as out, \
         JsonlWriter(stage_paths.errors_path) as err:

        for record in stream_jsonl(input_path):
            input_count += 1
            missing = missing_fields(record, DISCOVERED_LINK_REQUIRED)
            if missing:
                err.write({
                    "run_id": run_id,
                    "stage_name": "score_candidate_urls",
                    "source_lead_id": record.get("source_lead_id"),
                    "discovered_url": record.get("discovered_url"),
                    "error_type": "invalid_input_record",
                    "message": f"Missing required fields: {sorted(missing)}",
                    "retryable": False,
                    "created_at": started_at,
                })
                error_count += 1
                continue

            link_record = LinkRecord(
                discovered_url=record["discovered_url"],
                link_text=record["link_text"],
                is_internal=record["is_internal"],
                follow_allowed=record["follow_allowed"],
            )

            result = score_discovered_link(link_record, config=config)
            scored_at = datetime.now(timezone.utc).isoformat()

            if result.candidate_status == CandidateStatus.SELECTED:
                selected_count += 1
            elif result.candidate_status == CandidateStatus.EXTERNAL_REFERENCE:
                external_reference_count += 1
            else:
                rejected_count += 1

            if result.candidate_strength == CandidateStrength.STRONG:
                strong_count += 1
            elif result.candidate_strength == CandidateStrength.MEDIUM:
                medium_count += 1
            else:
                weak_count += 1

            out.write({
                "run_id": run_id,
                "source_lead_id": record["source_lead_id"],
                "source_url": record["source_url"],
                "candidate_url": record["discovered_url"],
                "link_text": record["link_text"],
                "candidate_type": result.candidate_type,
                "candidate_score": result.candidate_score,
                "candidate_status": result.candidate_status,
                "candidate_strength": result.candidate_strength,
                "score_reasons": result.score_reasons,
                "scored_at": scored_at,
            })
            output_count += 1

    completed_at = datetime.now(timezone.utc).isoformat()

    counts = {
        "input_records": input_count,
        "output_records": output_count,
        "error_records": error_count,
        "selected_count": selected_count,
        "rejected_count": rejected_count,
        "external_reference_count": external_reference_count,
        "strong_candidate_count": strong_count,
        "medium_candidate_count": medium_count,
        "weak_candidate_count": weak_count,
    }

    summary = {
        "stage_name": "score_candidate_urls",
        "stage_number": "03",
        "run_id": run_id,
        **counts,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    write_json(stage_paths.summary_path, summary)

    return StageResult(
        stage_id="03_score_candidate_urls",
        stage_number="03",
        stage_name="score_candidate_urls",
        status=STAGE_STATUS_COMPLETED,
        consumed_artifacts=[input_path.name],
        produced_artifacts=[stage_paths.output_path.name],
        summary_artifact=stage_paths.summary_path.name,
        error_artifact=stage_paths.errors_path.name,
        counts=counts,
        started_at=started_at,
        completed_at=completed_at,
    )
