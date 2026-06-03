from dataclasses import dataclass

from farmles_harvester.constants import CandidateStrength

_STRENGTH_RANK = {
    CandidateStrength.WEAK: 0,
    CandidateStrength.MEDIUM: 1,
    CandidateStrength.STRONG: 2,
}


@dataclass
class EvalVerdict:
    should_process: bool
    reasons: list[str]


def _is_permanent_failure(row: dict) -> bool:
    return row.get("last_outcome_class") not in (None, "ok") and row.get("retry_posture") == "permanent"


def evaluate_url_strength(
    row: dict | None,
    *,
    min_strength: str = CandidateStrength.STRONG,
    skip_permanent_failures: bool = True,
) -> EvalVerdict:
    if row is None:
        return EvalVerdict(True, ["new"])
    if skip_permanent_failures and _is_permanent_failure(row):
        return EvalVerdict(False, ["permanent failure"])
    rank = _STRENGTH_RANK.get(row.get("candidate_strength"), -1)
    threshold = _STRENGTH_RANK.get(min_strength, _STRENGTH_RANK[CandidateStrength.STRONG])
    if rank >= threshold:
        return EvalVerdict(True, [f"strength {row.get('candidate_strength')} >= {min_strength}"])
    return EvalVerdict(False, [f"strength {row.get('candidate_strength')} < {min_strength}"])


def rate_markdown_strength(
    word_count: int,
    *,
    strong_min: int = 300,
    medium_min: int = 100,
) -> str:
    """Return 'strong', 'medium', or 'weak' based on markdown word count."""
    if word_count >= strong_min:
        return CandidateStrength.STRONG
    if word_count >= medium_min:
        return CandidateStrength.MEDIUM
    return CandidateStrength.WEAK


def evaluate_markdown_strength(
    row: dict | None,
    *,
    min_word_count: int = 150,
    skip_permanent_failures: bool = True,
) -> EvalVerdict:
    if row is None:
        return EvalVerdict(True, ["new"])
    if skip_permanent_failures and _is_permanent_failure(row):
        return EvalVerdict(False, ["permanent failure"])
    words = row.get("markdown_word_count") or 0
    if words >= min_word_count:
        return EvalVerdict(True, [f"markdown_word_count {words} >= {min_word_count}"])
    return EvalVerdict(False, [f"markdown_word_count {words} < {min_word_count}"])
