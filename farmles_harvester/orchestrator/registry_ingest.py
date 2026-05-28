from pathlib import Path

from farmles_harvester.pipeline.jsonl import stream_jsonl
from farmles_harvester.registry.url_registry import UrlRegistry

_FETCH_STATUS_OUTCOME = {
    "fetched": ("ok", None),
    "timeout": ("timeout", "transient"),
    "fetch_error": ("connect_error", "transient"),
    "non_html": ("wrong_content_type", "permanent"),
}


def ingest_urls(
    registry: UrlRegistry,
    discovered_path: Path,
    candidate_path: Path,
    run_id: str,
) -> None:
    candidate_fields: dict[str, dict] = {}
    if candidate_path.exists():
        for rec in stream_jsonl(candidate_path):
            url = rec.get("candidate_url")
            if not url:
                continue
            candidate_fields[url] = {
                "candidate_score": rec.get("candidate_score"),
                "candidate_status": rec.get("candidate_status"),
                "candidate_strength": rec.get("candidate_strength"),
                "candidate_type": rec.get("candidate_type"),
            }

    if not discovered_path.exists():
        return

    # Per URL: representative source/lead and the full set of distinct sources.
    representative: dict[str, dict] = {}
    sources_by_url: dict[str, list[str]] = {}
    for rec in stream_jsonl(discovered_path):
        url = rec.get("discovered_url")
        source_url = rec.get("source_url")
        if not url or not source_url:
            continue
        if url not in representative:
            representative[url] = {
                "source_url": source_url,
                "source_lead_id": rec.get("source_lead_id"),
            }
            sources_by_url[url] = [source_url]
        elif source_url not in sources_by_url[url]:
            sources_by_url[url].append(source_url)

    rows = []
    for url, rep in representative.items():
        row = {
            "url": url,
            "source_url": rep["source_url"],
            "source_lead_id": rep["source_lead_id"],
            **candidate_fields.get(url, {}),
        }
        rows.append(row)

    registry.upsert_many(rows, run_id=run_id)

    # Extra sources beyond the representative one: link without bumping times_seen.
    for url, sources in sources_by_url.items():
        for extra_source in sources[1:]:
            registry.record_source(url, extra_source)


def ingest_fetch_outcomes(
    registry: UrlRegistry,
    markdown_path: Path,
    discover_errors_path: Path,
    run_id: str,
) -> None:
    if markdown_path.exists():
        for rec in stream_jsonl(markdown_path):
            url = rec.get("candidate_url")
            status = rec.get("fetch_status")
            mapping = _FETCH_STATUS_OUTCOME.get(status)
            if not url or mapping is None:
                continue
            outcome_class, retry_posture = mapping
            registry.record_outcome(
                url,
                outcome_class=outcome_class,
                retry_posture=retry_posture,
                detail={"http_status": rec.get("http_status")},
                run_id=run_id,
            )

    if discover_errors_path.exists():
        for rec in stream_jsonl(discover_errors_path):
            if rec.get("error_type") != "fetch_error":
                continue
            url = rec.get("source_url")
            if not url:
                continue
            registry.record_outcome(
                url,
                outcome_class="connect_error",
                retry_posture="transient",
                detail=rec.get("message"),
                run_id=run_id,
            )


def ingest_markdown_outcomes(
    registry: UrlRegistry,
    markdown_path: Path,
    run_id: str,
) -> None:
    if not markdown_path.exists():
        return
    for rec in stream_jsonl(markdown_path):
        if rec.get("fetch_status") != "fetched":
            continue
        url = rec.get("candidate_url")
        if not url:
            continue
        registry.record_markdown_outcome(
            url,
            status="generated",
            word_count=rec.get("markdown_word_count"),
            path=rec.get("markdown_path"),
            run_id=run_id,
        )


def ingest_source_relevance(
    registry: UrlRegistry,
    relevance_path: Path,
    slug_to_source_url: dict[str, str],
    run_id: str,
) -> None:
    if not relevance_path.exists():
        return
    rows = []
    for rec in stream_jsonl(relevance_path):
        slug = rec.get("source_slug")
        source_url = slug_to_source_url.get(slug)
        if not source_url:
            continue
        rows.append({
            "source_url": source_url,
            "relevance_label": rec.get("relevance_label"),
            "relevance_score": rec.get("relevance_score"),
            "keyword_hits": rec.get("keyword_hits"),
            "negative_hits": rec.get("negative_hits"),
            "total_word_count": rec.get("total_word_count"),
            "page_count": rec.get("page_count"),
        })
    registry.upsert_source_many(rows, run_id=run_id)
