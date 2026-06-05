"""Full end-to-end pipeline integration test that exercises the dynamic pipeline.

Seeds the pipeline with the fixture root index, which links to both static and
dynamic subpages via plain <a> tags. Stage 02 discovers those links via HTTP;
stage 04 classifies the dynamic subpages (js-market, nextjs-shell) as dynamic_js,
and the orchestrator routes them into stage d01 for browser-based re-fetch via
Crawl4AIFetcher.

The fixture root index is at:
    https://asrapartners.github.io/farmles_harvester/

It links to:
    static/basic/         → selected by stage 03, fetched in 04 as static_html
    dynamic/js-market/    → selected by stage 03 ("market" keyword), fetched in 04
                            as dynamic_js (empty SPA shell), browser-fetched by d01
    dynamic/nextjs-shell/ → rejected by stage 03 (no market keyword, score < 40)

Stage d01 browser-fetches js-market and captures the JS-injected "Greenfield"
market content that the plain HTTP fetcher cannot see.

Verifies:
  - All 7 static stages (00–06) complete successfully
  - Stage 04 classifies at least one page as dynamic_js
  - Stage d01 runs (status == "completed", not "skipped") with at least one OK result
  - The browser-fetched markdown contains the JS-injected "Greenfield" content
  - The url_registry correctly reflects URL outcomes after the dynamic fetch

Usage:
    pytest -m integration tests/integration/test_full_pipeline_dynamic.py -v -s
"""
import json

import pytest

from farmles_harvester.orchestrator.manifest import read_manifest
from farmles_harvester.orchestrator.run_pipeline import run_pipeline
from farmles_harvester.pipeline.jsonl import read_jsonl
from farmles_harvester.registry.url_registry import UrlRegistry

# The fixture root index has real <a> tags linking to dynamic subpages, which
# stage 02 can discover via HTTP fetch and stage 04 will classify as dynamic_js.
_SEED_URL = "https://asrapartners.github.io/farmles_harvester/"

_REQUIRED_STAGES = [
    "00_normalize_source_leads",
    "01_validate_urls",
    "02_discover_links",
    "03_score_candidate_urls",
    "04_generate_markdown_pages",
    "05_strip_boilerplate_blocks",
    "06_score_source_relevance",
]


@pytest.mark.integration
def test_full_pipeline_dynamic_fixture(tmp_path):
    seed = tmp_path / "seed_urls.txt"
    seed.write_text(f"{_SEED_URL}\n", encoding="utf-8")
    registry_db = tmp_path / "url_registry.db"

    run_dir = run_pipeline(
        seed_file=seed,
        tag="e2e-dynamic",
        runs_dir=tmp_path / "runs",
        config={"fast_mode": False},
        registry_db=registry_db,
    )

    manifest = read_manifest(run_dir / "manifest.json")
    records_04 = read_jsonl(run_dir / "04_markdown_pages.jsonl")

    d01_jsonl = run_dir / "d01_browser_fetched_pages.jsonl"
    records_d01 = read_jsonl(d01_jsonl) if d01_jsonl.exists() else []

    # All static stages must complete
    for stage_id in _REQUIRED_STAGES:
        status = manifest["stages"].get(stage_id, {}).get("status")
        assert status == "completed", (
            f"Stage {stage_id} did not complete (status={status!r}):\n"
            + json.dumps(manifest["stages"].get(stage_id, {}), indent=2)
        )

    # Stage 04 must have classified the page as dynamic_js
    dynamic_records_04 = [r for r in records_04 if r.get("render_type") == "dynamic_js"]
    if not dynamic_records_04:
        from collections import Counter
        render_types = Counter(r.get("render_type", "missing") for r in records_04)
        pytest.fail(
            f"Stage 04 produced no dynamic_js records — classifier did not fire.\n"
            f"render_type breakdown: {dict(render_types)}\n"
            f"Records ({len(records_04)} total):\n"
            + "\n".join(
                f"  {r.get('render_type', '?')}  {r.get('candidate_url', '?')}"
                for r in records_04
            )
        )

    # Stage d01 must have run (not skipped)
    d01_stage = manifest["stages"].get("d01_browser_fetched_pages", {})
    d01_status = d01_stage.get("status", "unknown")
    d01_counts = d01_stage.get("counts", {})

    assert d01_status == "completed", (
        f"Stage d01 did not complete (status={d01_status!r}) — "
        f"dynamic pipeline was not triggered.\n"
        + json.dumps(d01_stage, indent=2)
    )

    assert d01_counts.get("ok", 0) >= 1, (
        f"Stage d01 completed but no pages were successfully browser-fetched.\n"
        f"Counts: {d01_counts}\n"
        f"d01 records ({len(records_d01)} total):\n"
        + "\n".join(
            f"  {r.get('fetch_status', '?')}  wc={r.get('word_count', '?')}  "
            f"{r.get('candidate_url', '?')}"
            for r in records_d01
        )
    )

    # Browser-fetched markdown must contain the JS-injected content
    ok_d01 = [r for r in records_d01 if r.get("fetch_status") == "ok"]
    assert ok_d01, "No ok records in d01_browser_fetched_pages.jsonl"

    best = max(ok_d01, key=lambda r: r.get("word_count", 0))
    md_path = run_dir / best["markdown_path"]
    assert md_path.exists(), f"Browser-fetched markdown file not found: {md_path}"

    markdown = md_path.read_text(encoding="utf-8")
    word_count = len(markdown.split())

    assert word_count >= 50, (
        f"Browser-fetched page has only {word_count} words — content too thin.\n"
        f"{markdown[:400]}"
    )
    assert "Greenfield" in markdown, (
        f"Expected 'Greenfield' in browser-rendered markdown from {best.get('candidate_url')}.\n"
        f"Got {word_count} words:\n{markdown[:600]}"
    )

    # Registry must reflect correct URL outcomes
    with UrlRegistry(registry_db) as reg:
        total_urls = reg.count()
        urls_ok = reg.count(where="last_outcome_class = 'ok'")
        urls_generated = reg.count(where="markdown_status = 'generated'")
        source_rec = reg.get_source(_SEED_URL)

    assert total_urls > 0, "Registry is empty after full pipeline run"
    assert urls_ok > 0, "No URLs have outcome_class='ok' in registry"
    assert urls_generated > 0, "No URLs have markdown_status='generated' in registry"
    assert source_rec is not None, (
        f"Source {_SEED_URL!r} missing from registry sources table after stage 06"
    )

    _print_stats(
        run_dir=run_dir,
        records_04=records_04,
        dynamic_records_04=dynamic_records_04,
        best=best,
        word_count=word_count,
        total_urls=total_urls,
        urls_ok=urls_ok,
        urls_generated=urls_generated,
        d01_status=d01_status,
        d01_counts=d01_counts,
    )


def _print_stats(*, run_dir, records_04, dynamic_records_04, best, word_count,
                  total_urls, urls_ok, urls_generated, d01_status, d01_counts):
    from collections import Counter
    render_types = Counter(r.get("render_type", "unknown") for r in records_04)

    print()
    print("=" * 66)
    print("  Full Pipeline Dynamic Integration Test — Results")
    print("=" * 66)
    print(f"  Seed URL        : {_SEED_URL}")
    print(f"  Run directory   : {run_dir}")
    print()
    print("  Stage 04 — Markdown Generation")
    print(f"    Total candidates  : {len(records_04)}")
    for rtype, count in sorted(render_types.items()):
        print(f"    render_type={rtype:<12}: {count}")
    print()
    print("  Stage D01 — Dynamic Browser Fetch")
    print(f"    Status            : {d01_status}")
    print(f"    OK                : {d01_counts.get('ok', 0)}")
    print(f"    Thin content      : {d01_counts.get('thin_content', 0)}")
    print(f"    Failed            : {d01_counts.get('failed', 0)}")
    print(f"    Best page URL     : {best.get('candidate_url', '?')}")
    print(f"    Best word count   : {word_count}")
    print()
    print("  URL Registry")
    print(f"    Total URLs        : {total_urls}")
    print(f"    Outcome OK        : {urls_ok}")
    print(f"    Markdown generated: {urls_generated}")
    print("=" * 66)
    print()
