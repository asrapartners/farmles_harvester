import re

from farmles_harvester.constants import SourceRelevanceLabel

_MARKET_KEYWORDS: frozenset[str] = frozenset({
    "farmer", "farmers", "market", "vendor", "vendors", "produce",
    "organic", "food", "harvest", "seasonal", "booth", "stall",
    "fresh", "local", "grower", "growers", "artisan", "farmstand",
    "farm", "csa", "agri",
})

_NON_MARKET_SIGNALS: frozenset[str] = frozenset({
    "township", "municipality", "zoning", "ordinance", "government",
    "council", "commissioner", "supervisor", "police", "fire",
    "emergency", "utilities",
})

_SOURCE_FOOTER = re.compile(r"\n---\n\nSource:.*$", re.DOTALL)


def _strip_md_frame(text: str) -> str:
    """Remove the title line and ---\\n\\nSource: footer, returning only the body."""
    lines = text.splitlines()
    # Drop first non-empty line (page title)
    body_lines = lines[1:] if lines else []
    body = "\n".join(body_lines)
    body = _SOURCE_FOOTER.sub("", body)
    return body.strip()


def score_md_text(text: str) -> dict:
    """Score a single MD file's content for market relevance.

    Returns raw counts: keyword_hits, negative_hits, word_count.
    """
    body = _strip_md_frame(text)
    words = re.findall(r"[a-z]+", body.lower())
    word_set = set(words)

    keyword_hits = sum(1 for w in words if w in _MARKET_KEYWORDS)
    negative_hits = sum(1 for w in word_set if w in _NON_MARKET_SIGNALS)

    return {
        "keyword_hits": keyword_hits,
        "negative_hits": negative_hits,
        "word_count": len(words),
    }


_LABEL_RANK = {
    SourceRelevanceLabel.LOW_CONFIDENCE: 0,
    SourceRelevanceLabel.UNCERTAIN: 1,
    SourceRelevanceLabel.LIKELY: 2,
    SourceRelevanceLabel.CONFIRMED: 3,
}


def _label_for_page(keyword_hits: int, word_count: int, cfg: dict) -> str:
    score = keyword_hits * 10
    if score >= cfg["confirmed_score"] and word_count >= cfg["confirmed_words"]:
        return SourceRelevanceLabel.CONFIRMED
    if score >= cfg["likely_score"] and word_count >= cfg["likely_words"]:
        return SourceRelevanceLabel.LIKELY
    if score >= cfg["uncertain_min_score"] or word_count >= cfg["uncertain_min_words"]:
        return SourceRelevanceLabel.UNCERTAIN
    return SourceRelevanceLabel.LOW_CONFIDENCE


def score_source(md_texts: list[str], config: dict | None = None) -> dict:
    """Assign a relevance label to a source based on its MD pages.

    The source label is the best (highest confidence) label found on any
    single page — so one strong page is enough to mark the source confirmed.
    Aggregate totals are also returned for reporting.
    """
    cfg = {
        "confirmed_score": (config or {}).get("confirmed_score", 30),
        "confirmed_words": (config or {}).get("confirmed_words", 200),
        "likely_score": (config or {}).get("likely_score", 10),
        "likely_words": (config or {}).get("likely_words", 50),
        "uncertain_min_score": (config or {}).get("uncertain_min_score", 1),
        "uncertain_min_words": (config or {}).get("uncertain_min_words", 20),
    }

    total_keyword_hits = 0
    total_negative_hits = 0
    total_word_count = 0
    best_label = SourceRelevanceLabel.LOW_CONFIDENCE

    for text in md_texts:
        counts = score_md_text(text)
        total_keyword_hits += counts["keyword_hits"]
        total_negative_hits += counts["negative_hits"]
        total_word_count += counts["word_count"]

        page_label = _label_for_page(counts["keyword_hits"], counts["word_count"], cfg)
        if _LABEL_RANK[page_label] > _LABEL_RANK[best_label]:
            best_label = page_label

    relevance_score = max(0, (total_keyword_hits * 10) - (total_negative_hits * 5))

    return {
        "relevance_score": relevance_score,
        "relevance_label": best_label,
        "keyword_hits": total_keyword_hits,
        "negative_hits": total_negative_hits,
        "total_word_count": total_word_count,
        "page_count": len(md_texts),
    }
