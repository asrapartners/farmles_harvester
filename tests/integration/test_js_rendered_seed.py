"""Integration test exposing the JS-rendered seed discovery bug.

Bug
---
When the seed URL is itself a JS-rendered page (empty SPA shell), stage 02 fetches
it via plain HTTP, sees no real <a> tags (they are injected by JavaScript at runtime),
and writes zero records to 02_discovered_links.jsonl. Stages 03 and 04 then have no
candidates, stage d01 never runs, and the seed URL is silently dropped — the pipeline
completes with no content extracted at all.

Reproducer
----------
Seed URL: https://asrapartners.github.io/farmles_harvester/dynamic/js-market/
- The page source is <div id="app"></div> followed by a <script> that injects 200+
  words of "Greenfield Farmers Market" content into #app at runtime.
- An HTTP fetcher sees the bare shell and finds zero <a href> links.
- detect_render_type() correctly classifies it as "dynamic_js", but it never gets the
  chance to do so because no candidate record is ever created for the seed URL.

Legitimate fixes (any one would make this test pass)
----------------------------------------------------
1. Stage 02 dynamic fallback — if HTTP fetch of the source URL yields an empty-shell
   render type, re-fetch with Crawl4AI to extract links from the JS-rendered DOM before
   continuing.
2. Include the source URL itself as a candidate — pass the seed URL directly into
   stage 04 as a candidate alongside the discovered links. If the seed page classifies
   as dynamic_js, it enters d01 naturally.
3. Pre-classify seeds before link discovery — run render-type detection in stage 01 or
   02, and for dynamic_js sources use Crawl4AI for link extraction instead.

Usage:
    pytest -m integration tests/integration/test_js_rendered_seed.py -v -s
"""
import pytest

from farmles_harvester.orchestrator.run_pipeline import run_pipeline
from farmles_harvester.pipeline.jsonl import read_jsonl

_SEED_URL = "https://asrapartners.github.io/farmles_harvester/dynamic/js-market/"


@pytest.mark.integration
def test_js_rendered_seed_is_not_dropped(tmp_path):
    """A JS-rendered seed URL must not be silently dropped by the pipeline.

    The pipeline should produce some processed output for the seed URL — either
    stage 04 classifying it as dynamic_js, or stage d01 browser-fetching it.

    Currently FAILS: stage 02 HTTP-fetches the empty SPA shell, finds zero <a> tags,
    and produces zero discovered links → stage 04 receives no candidates → d01 never
    runs → no content is extracted from the seed URL.
    """
    seed = tmp_path / "seed_urls.txt"
    seed.write_text(f"{_SEED_URL}\n", encoding="utf-8")

    run_dir = run_pipeline(
        seed_file=seed,
        tag="e2e-js-seed",
        runs_dir=tmp_path / "runs",
        config={"fast_mode": False},
        registry_db=tmp_path / "url_registry.db",
    )

    records_04 = read_jsonl(run_dir / "04_markdown_pages.jsonl")
    d01_jsonl = run_dir / "d01_browser_fetched_pages.jsonl"
    records_d01 = read_jsonl(d01_jsonl) if d01_jsonl.exists() else []

    def _matches_seed(url: str) -> bool:
        return url.rstrip("/") == _SEED_URL.rstrip("/")

    seed_in_04 = any(_matches_seed(r.get("candidate_url", "")) for r in records_04)
    seed_in_d01 = any(_matches_seed(r.get("candidate_url", "")) for r in records_d01)

    assert seed_in_04 or seed_in_d01, (
        f"JS-rendered seed URL was silently dropped — no pipeline stage produced output for it.\n\n"
        f"Seed URL : {_SEED_URL}\n"
        f"Stage 04 candidates ({len(records_04)} total):\n"
        + (
            "\n".join(f"  {r.get('candidate_url')}" for r in records_04)
            or "  (none)"
        )
        + f"\n\nStage d01 records ({len(records_d01)} total):\n"
        + (
            "\n".join(f"  {r.get('candidate_url')}" for r in records_d01)
            or "  (none)"
        )
        + "\n\nRoot cause: stage 02 HTTP-fetches the SPA shell, sees no <a> tags "
        "(links are inside a JS string), and writes zero discovered links. The seed "
        "URL never enters stage 04 or d01."
    )
