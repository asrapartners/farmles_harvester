import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from farmles_harvester.constants import CandidateType, CandidateStatus, CandidateStrength

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
