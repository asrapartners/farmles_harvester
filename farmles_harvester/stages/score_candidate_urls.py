import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from farmles_harvester.constants import CandidateType, CandidateStatus, CandidateStrength
from farmles_harvester.models.record_contracts import DISCOVERED_LINK_REQUIRED, missing_fields
from farmles_harvester.pipeline.jsonl import JsonlWriter, stream_jsonl, write_json
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult

_POSITIVE_SIGNAL_GROUPS: list[tuple[frozenset[str], str, int]] = [
    # Vendor / farmer discovery
    (frozenset({"vendor", "vendors", "our-vendors", "sell"}),
     CandidateType.VENDOR_PAGE, 50),
    # Location / hours
    (frozenset({"hours", "schedule", "open"}), CandidateType.HOURS_LOCATION_PAGE, 40),
    (frozenset({"visit", "location", "directions", "parking", "map"}), CandidateType.HOURS_LOCATION_PAGE, 40),
    # Events / calendar
    (frozenset({"calendar", "events", "opening-day"}), CandidateType.CALENDAR_EVENTS_PAGE, 40),
    # About / contact / mission
    (frozenset({"about", "contact", "faq", "faqs", "mission", "history", "staff"}),
     CandidateType.ABOUT_CONTACT_PAGE, 35),
    # General market info — also catches "certified-farmers-markets" via "certified"/"farmers" tokens
    (frozenset({"market", "markets", "farmers-market", "certified", "cfm", "farmer", "farmers"}),
     CandidateType.GENERAL_MARKET_PAGE, 30),
    # Food / produce signals
    (frozenset({"food", "drink", "eat"}),
     CandidateType.GENERAL_MARKET_PAGE, 30),
    # Farmer's market nutrition program acronyms — high confidence signals
    (frozenset({"fmnp", "sfmnp", "snap", "ebt", "wic"}),
     CandidateType.GENERAL_MARKET_PAGE, 45),
]

# External domains whose presence as a discovered link is a strong signal the
# source is a certified farmer's market — boosts all internal rejected candidates.
_PROGRAM_LINK_DOMAINS = frozenset({
    "fns.usda.gov",       # USDA Food & Nutrition Service (SFMNP, SNAP, WIC)
    "ams.usda.gov",       # USDA Agricultural Marketing Service (farmers market programs)
    "marketmatch.org",    # Market Match EBT doubling program
})
_PROGRAM_LINK_BOOST = 25

_HARD_REJECT = frozenset({"privacy", "terms", "cookies", "login", "cart", "checkout", "wp-admin", "cdn-cgi"})
_SOFT_PENALTY = frozenset({
    "feed", "rss", "tag", "tags", "category", "author",
    "blog", "archive", "covid",
    "recipe", "recipes",
    "video", "videos",
    "market-match",  # EBT/CalFresh program page, not a market info page
    "page",          # pagination query param (?page=N)
})

_DEFAULT_SELECTED_THRESHOLD = 40
_DEFAULT_STRONG_THRESHOLD = 70


@dataclass
class LinkRecord:
    """Input to score_discovered_link: a single discovered link with its context."""

    discovered_url: str
    link_text: str
    is_internal: bool
    follow_allowed: bool = True


@dataclass
class CandidateScore:
    """Output of score_discovered_link: scoring result for a single link."""

    candidate_score: int
    candidate_type: str
    candidate_status: str
    candidate_strength: str
    score_reasons: list[str]


def _tokenize(url: str, text: str) -> set[str]:
    parsed = urlparse(url)
    path = parsed.path.lower()
    raw_segments = {s for s in path.split("/") if s}
    word_tokens = {t for t in re.split(r"[/\-_]+", path) if t}
    text_tokens = set(text.lower().split())
    query_keys = set(parse_qs(parsed.query).keys())
    return raw_segments | word_tokens | text_tokens | query_keys


def score_discovered_link(link_record: LinkRecord, config: dict | None = None) -> CandidateScore:
    """Pure scoring function: apply token-based rules to a link and return its CandidateScore."""
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

    # Extra penalty for explicit page numbers > 1 (duplicate paginated views)
    page_vals = parse_qs(urlparse(link_record.discovered_url).query).get("page", [])
    if page_vals:
        try:
            if int(page_vals[0]) > 1:
                score -= 60
                reasons.append(f"-60 paginated view (page={page_vals[0]})")
        except ValueError:
            pass

    # Hard-reject WordPress/social share URLs (?share=facebook, ?share=twitter, etc.)
    # These return empty content — the share param triggers a social redirect, not a real page.
    share_vals = parse_qs(urlparse(link_record.discovered_url).query).get("share", [])
    if share_vals:
        score = 0
        hard_rejected = True
        candidate_type = CandidateType.LOW_VALUE_PAGE
        reasons.append(f"-100 social share URL (?share={share_vals[0]})")

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


def _is_homepage(url: str) -> bool:
    return urlparse(url).path in ("", "/")


def run_score_candidate_urls(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
) -> StageResult:
    """Stage 03: score every discovered link and select candidates for crawling.

    Reads 02_discovered_links.jsonl, applies score_discovered_link() to each
    record, and writes:
      - 03_candidate_urls.jsonl  (all scored records, selected and rejected)
      - 03_candidate_urls_errors.jsonl  (unexpected stage-level failures)
      - 03_candidate_urls_summary.json
    Returns a StageResult with per-strength counts.
    """
    started_at = datetime.now(timezone.utc).isoformat()

    # --- Pass 1: score every record, collect into memory ---
    scored_rows: list[dict] = []
    error_rows: list[dict] = []

    for record in stream_jsonl(input_path):
        missing = missing_fields(record, DISCOVERED_LINK_REQUIRED)
        if missing:
            error_rows.append({
                "run_id": run_id,
                "stage_name": "score_candidate_urls",
                "source_slug": record.get("source_slug"),
                "discovered_url": record.get("discovered_url"),
                "error_type": "invalid_input_record",
                "message": f"Missing required fields: {sorted(missing)}",
                "retryable": False,
                "created_at": started_at,
            })
            continue

        link_record = LinkRecord(
            discovered_url=record["discovered_url"],
            link_text=record["link_text"],
            is_internal=record["is_internal"],
            follow_allowed=record["follow_allowed"],
        )
        result = score_discovered_link(link_record, config=config)
        scored_rows.append({
            "run_id": run_id,
            "source_slug": record["source_slug"],
            "source_url": record["source_url"],
            "input_url": record.get("input_url"),
            "normalized_url": record.get("normalized_url"),
            "candidate_url": record["discovered_url"],
            "link_text": record["link_text"],
            "candidate_type": result.candidate_type,
            "candidate_score": result.candidate_score,
            "candidate_status": result.candidate_status,
            "candidate_strength": result.candidate_strength,
            "score_reasons": result.score_reasons,
            "scored_at": datetime.now(timezone.utc).isoformat(),
        })

    # --- Pass 2: find sources with meaningful selections or program links ---
    leads_with_meaningful_selections: set[str] = {
        row["source_slug"]
        for row in scored_rows
        if row["candidate_status"] == CandidateStatus.SELECTED
        and row["candidate_score"] > 20
        and not _is_homepage(row["candidate_url"])
    }

    # Sources whose discovered links include an authoritative program domain
    # (e.g. fns.usda.gov) — strong signal the source is a certified market.
    leads_with_program_links: set[str] = {
        row["source_slug"]
        for row in scored_rows
        if row["candidate_status"] == CandidateStatus.EXTERNAL_REFERENCE
        and urlparse(row["candidate_url"]).netloc in _PROGRAM_LINK_DOMAINS
    }

    # --- Pass 3: promote homepages + apply program-link boost ---
    homepage_promoted_count = 0
    program_boosted_count = 0

    for row in scored_rows:
        lead = row["source_slug"]
        is_internal_rejected = (
            row["candidate_status"] == CandidateStatus.REJECTED
            and row["candidate_type"] != CandidateType.EXTERNAL_REFERENCE
        )

        # Apply program-link boost before promotion checks so the boosted
        # score feeds into the threshold comparison.
        if is_internal_rejected and lead in leads_with_program_links:
            new_score = min(100, row["candidate_score"] + _PROGRAM_LINK_BOOST)
            row["candidate_score"] = new_score
            row["score_reasons"] = row["score_reasons"] + [f"+{_PROGRAM_LINK_BOOST} program link boost (authoritative external domain)"]
            if new_score >= (config or {}).get("selected_threshold", _DEFAULT_SELECTED_THRESHOLD):
                row["candidate_status"] = CandidateStatus.SELECTED
                row["candidate_strength"] = CandidateStrength.MEDIUM
                program_boosted_count += 1

        # Promote rejected homepages for sources with meaningful sub-page selections.
        if (
            row["candidate_status"] == CandidateStatus.REJECTED
            and _is_homepage(row["candidate_url"])
            and lead in leads_with_meaningful_selections
        ):
            row["candidate_status"] = CandidateStatus.SELECTED
            row["candidate_strength"] = CandidateStrength.MEDIUM
            row["score_reasons"] = row["score_reasons"] + ["homepage promoted: source has meaningful sub-page selections"]
            homepage_promoted_count += 1

    # --- Write output ---
    input_count = len(scored_rows) + len(error_rows)
    output_count = 0
    error_count = len(error_rows)
    selected_count = 0
    rejected_count = 0
    external_reference_count = 0
    strong_count = 0
    medium_count = 0
    weak_count = 0

    with JsonlWriter(stage_paths.output_path) as out, \
         JsonlWriter(stage_paths.errors_path) as err:

        for row in error_rows:
            err.write(row)

        for row in scored_rows:
            status = row["candidate_status"]
            strength = row["candidate_strength"]

            if status == CandidateStatus.SELECTED:
                selected_count += 1
            elif status == CandidateStatus.EXTERNAL_REFERENCE:
                external_reference_count += 1
            else:
                rejected_count += 1

            if strength == CandidateStrength.STRONG:
                strong_count += 1
            elif strength == CandidateStrength.MEDIUM:
                medium_count += 1
            else:
                weak_count += 1

            out.write(row)
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
        "homepage_promoted_count": homepage_promoted_count,
        "program_boosted_count": program_boosted_count,
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
