"""Integration test: verify Crawl4AIFetcher converts JS-rendered content to markdown.

The fixture page at tests/fixtures/sites/dynamic/js-market/index.html is an SPA shell
whose body is empty HTML. A synchronous <script> injects rich market content into
<div id="app">, which only a real browser can see. This test confirms the browser-based
fetcher captures that content while a plain HTTP fetcher would not.

Requires the fixture to be deployed to GitHub Pages (pushed to main on tests/fixtures/sites/**).

Usage:
    pytest -m integration tests/integration/test_crawl4ai_dynamic_pipeline.py -v
"""
import pytest

from farmles_harvester.web.crawl4ai_fetcher import Crawl4AIFetcher

_JS_MARKET_URL = "https://asrapartners.github.io/farmles_harvester/dynamic/js-market/"
_MIN_WORD_COUNT = 150


@pytest.mark.integration
def test_js_rendered_content_converted_to_markdown(tmp_path):
    """Browser fetcher should extract JS-injected content that static HTTP cannot see."""
    md_path = tmp_path / "output.md"
    record = {
        "candidate_url": _JS_MARKET_URL,
        "source_slug": "js-market",
        "markdown_path": str(md_path),
    }

    fetcher = Crawl4AIFetcher(min_word_count=_MIN_WORD_COUNT)
    ok_results, error_records = fetcher.fetch_batch([record])

    assert not error_records, f"Expected no errors, got: {error_records}"
    assert len(ok_results) == 1

    result = ok_results[0]
    assert result["fetch_status"] == "ok"
    assert result["word_count"] >= _MIN_WORD_COUNT

    assert md_path.exists(), "Markdown file should have been written by the fetcher"
    markdown = md_path.read_text(encoding="utf-8")
    assert "Greenfield" in markdown, (
        f"Expected JS-injected content ('Greenfield') in markdown, got:\n{markdown[:500]}"
    )
