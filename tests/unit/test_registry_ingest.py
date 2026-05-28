from farmles_harvester.orchestrator.registry_ingest import (
    ingest_fetch_outcomes,
    ingest_markdown_outcomes,
    ingest_source_relevance,
    ingest_urls,
)
from farmles_harvester.pipeline.jsonl import write_jsonl
from farmles_harvester.registry import UrlRegistry
from farmles_harvester.web.url_utils import source_url_to_slug

RUN_ID = "run_ingest"


def _registry(tmp_path):
    return UrlRegistry(tmp_path / "r.sqlite")


class TestIngestUrls:
    def test_upserts_discovered_with_candidate_fields(self, tmp_path):
        discovered = tmp_path / "02.jsonl"
        candidate = tmp_path / "03.jsonl"
        write_jsonl(discovered, [
            {"discovered_url": "https://a.com/p1", "source_url": "https://a.com/", "source_lead_id": "lead_1"},
            {"discovered_url": "https://a.com/p2", "source_url": "https://a.com/", "source_lead_id": "lead_1"},
        ])
        write_jsonl(candidate, [
            {"candidate_url": "https://a.com/p1", "candidate_score": 70,
             "candidate_status": "selected", "candidate_strength": "high",
             "candidate_type": "vendor_page"},
        ])
        with _registry(tmp_path) as reg:
            ingest_urls(reg, discovered, candidate, RUN_ID)
            p1 = reg.get("https://a.com/p1")
            p2 = reg.get("https://a.com/p2")
            assert p1["candidate_score"] == 70
            assert p1["candidate_status"] == "selected"
            assert p1["last_run_id"] == RUN_ID
            assert p2 is not None
            assert p2["candidate_score"] is None

    def test_multi_source_url_counts_once_and_links_all(self, tmp_path):
        discovered = tmp_path / "02.jsonl"
        candidate = tmp_path / "03.jsonl"
        write_jsonl(discovered, [
            {"discovered_url": "https://x.com/shared", "source_url": "https://a.com/", "source_lead_id": "lead_a"},
            {"discovered_url": "https://x.com/shared", "source_url": "https://b.com/", "source_lead_id": "lead_b"},
        ])
        write_jsonl(candidate, [])
        with _registry(tmp_path) as reg:
            ingest_urls(reg, discovered, candidate, RUN_ID)
            row = reg.get("https://x.com/shared")
            assert row["times_seen"] == 1
            assert row["source_url_count"] == 2
            assert set(reg.sources_of("https://x.com/shared")) == {"https://a.com/", "https://b.com/"}


class TestIngestOutcomes:
    def test_fetch_and_markdown_outcomes(self, tmp_path):
        discovered = tmp_path / "02.jsonl"
        candidate = tmp_path / "03.jsonl"
        markdown = tmp_path / "04.jsonl"
        errors = tmp_path / "02_errors.jsonl"
        write_jsonl(discovered, [
            {"discovered_url": "https://a.com/ok", "source_url": "https://a.com/", "source_lead_id": "l"},
            {"discovered_url": "https://a.com/slow", "source_url": "https://a.com/", "source_lead_id": "l"},
        ])
        write_jsonl(candidate, [])
        write_jsonl(markdown, [
            {"candidate_url": "https://a.com/ok", "fetch_status": "fetched",
             "http_status": 200, "markdown_path": "generated_wiki/a/ok/index.md"},
            {"candidate_url": "https://a.com/slow", "fetch_status": "timeout", "http_status": None},
        ])
        write_jsonl(errors, [
            {"error_type": "fetch_error", "source_url": "https://a.com/ok", "message": "boom"},
        ])
        with _registry(tmp_path) as reg:
            ingest_urls(reg, discovered, candidate, RUN_ID)
            ingest_fetch_outcomes(reg, markdown, errors, RUN_ID)
            ingest_markdown_outcomes(reg, markdown, RUN_ID)

            slow = reg.get("https://a.com/slow")
            assert slow["last_outcome_class"] == "timeout"
            assert slow["retry_posture"] == "transient"

            ok = reg.get("https://a.com/ok")
            # discover error recorded after the "ok" markdown outcome
            assert ok["last_outcome_class"] == "connect_error"
            assert ok["markdown_status"] == "generated"
            assert ok["markdown_path"] == "generated_wiki/a/ok/index.md"


class TestIngestSourceRelevance:
    def test_upserts_sources_via_slug_map(self, tmp_path):
        source_url = "https://farm.example.com/"
        slug = source_url_to_slug(source_url)
        relevance = tmp_path / "06.jsonl"
        write_jsonl(relevance, [
            {"source_slug": slug, "relevance_label": "confirmed",
             "relevance_score": 120, "keyword_hits": 12, "negative_hits": 0,
             "total_word_count": 800, "page_count": 3},
        ])
        with _registry(tmp_path) as reg:
            ingest_source_relevance(reg, relevance, {slug: source_url}, RUN_ID)
            src = reg.get_source(source_url)
            assert src is not None
            assert src["relevance_label"] == "confirmed"
            assert src["relevance_score"] == 120
            assert src["page_count"] == 3
