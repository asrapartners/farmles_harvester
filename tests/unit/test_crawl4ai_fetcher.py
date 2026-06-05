import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from farmles_harvester.web.crawl4ai_fetcher import Crawl4AIFetcher

_RICH_MARKDOWN = ("word " * 200).strip()  # 200 words — safely above default threshold


def _make_crawl_result(url: str, success: bool, markdown: str = "", error: str = ""):
    cr = MagicMock()
    cr.url = url
    cr.success = success
    cr.error_message = error if not success else None
    md_obj = MagicMock()
    md_obj.fit_markdown = markdown
    md_obj.raw_markdown = markdown
    cr.markdown = md_obj
    return cr


def _make_records(tmp_path: Path, urls: list[str]) -> list[dict]:
    return [
        {
            "candidate_url": url,
            "source_slug": f"slug-{i}",
            "markdown_path": str(tmp_path / f"wiki/source-{i}/index.md"),
        }
        for i, url in enumerate(urls)
    ]


def _mock_sys_modules(crawl_results: list, arun_many_exc: Exception | None = None):
    """Return a sys.modules patch dict that stubs out crawl4ai."""
    mock_crawler = MagicMock()
    if arun_many_exc is not None:
        mock_crawler.arun_many = AsyncMock(side_effect=arun_many_exc)
    else:
        mock_crawler.arun_many = AsyncMock(return_value=crawl_results)

    mock_async_cm = MagicMock()
    mock_async_cm.__aenter__ = AsyncMock(return_value=mock_crawler)
    mock_async_cm.__aexit__ = AsyncMock(return_value=False)

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = MagicMock(return_value=mock_async_cm)
    mock_crawl4ai.BrowserConfig = MagicMock()
    mock_crawl4ai.CrawlerRunConfig = MagicMock()
    mock_crawl4ai.CacheMode = MagicMock()

    return {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.content_filter_strategy": MagicMock(),
        "crawl4ai.markdown_generation_strategy": MagicMock(),
    }


@pytest.fixture()
def fetcher():
    # min_word_count=1 so basic tests aren't affected by threshold logic
    return Crawl4AIFetcher(max_concurrent=2, use_cache=False, min_word_count=1)


@pytest.fixture()
def strict_fetcher():
    return Crawl4AIFetcher(max_concurrent=2, use_cache=False, min_word_count=150)


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------

def test_successful_fetch_writes_markdown_and_returns_result(tmp_path, fetcher):
    urls = ["https://example.com/a"]
    records = _make_records(tmp_path, urls)
    crawl_results = [_make_crawl_result(urls[0], success=True, markdown="# Hello\n\nWorld content here")]

    with patch.dict(sys.modules, _mock_sys_modules(crawl_results)):
        ok, errors = fetcher.fetch_batch(records)

    assert errors == []
    assert len(ok) == 1
    r = ok[0]
    assert r["candidate_url"] == urls[0]
    assert r["fetch_status"] == "ok"
    assert r["word_count"] == 5
    assert r["overwritten"] is False
    assert r["bytes_before"] == 0
    assert r["bytes_after"] > 0
    assert Path(records[0]["markdown_path"]).read_text() == "# Hello\n\nWorld content here"


def test_bytes_incr_pcnt_clamped_to_100(tmp_path, fetcher):
    urls = ["https://example.com/b"]
    records = _make_records(tmp_path, urls)
    md_path = Path(records[0]["markdown_path"])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("hi", encoding="utf-8")

    crawl_results = [_make_crawl_result(urls[0], success=True, markdown=_RICH_MARKDOWN)]

    with patch.dict(sys.modules, _mock_sys_modules(crawl_results)):
        ok, _ = fetcher.fetch_batch(records)

    assert ok[0]["overwritten"] is True
    assert ok[0]["bytes_before"] == 2
    assert ok[0]["bytes_incr_pcnt"] == 100.0


def test_bytes_incr_pcnt_partial_improvement(tmp_path, fetcher):
    urls = ["https://example.com/c"]
    records = _make_records(tmp_path, urls)
    md_path = Path(records[0]["markdown_path"])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    existing = "x" * 100
    md_path.write_text(existing, encoding="utf-8")

    new_content = "x" * 150
    crawl_results = [_make_crawl_result(urls[0], success=True, markdown=new_content)]

    with patch.dict(sys.modules, _mock_sys_modules(crawl_results)):
        ok, _ = fetcher.fetch_batch(records)

    assert ok[0]["bytes_before"] == 100
    assert ok[0]["bytes_after"] == 150
    assert ok[0]["bytes_incr_pcnt"] == 50.0


# ---------------------------------------------------------------------------
# failure handling — per-URL errors
# ---------------------------------------------------------------------------

def test_failed_fetch_produces_error_record_and_leaves_file_untouched(tmp_path, fetcher):
    urls = ["https://example.com/fail"]
    records = _make_records(tmp_path, urls)
    md_path = Path(records[0]["markdown_path"])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("original content", encoding="utf-8")

    crawl_results = [_make_crawl_result(urls[0], success=False, error="TimeoutError after 60s")]

    with patch.dict(sys.modules, _mock_sys_modules(crawl_results)):
        ok, errors = fetcher.fetch_batch(records)

    assert ok == []
    assert len(errors) == 1
    assert errors[0]["candidate_url"] == urls[0]
    assert errors[0]["fetch_status"] == "timeout"
    assert md_path.read_text() == "original content"


def test_non_timeout_failure_has_fetch_error_status(tmp_path, fetcher):
    urls = ["https://example.com/fail"]
    records = _make_records(tmp_path, urls)
    crawl_results = [_make_crawl_result(urls[0], success=False, error="DNS resolution failed")]

    with patch.dict(sys.modules, _mock_sys_modules(crawl_results)):
        _, errors = fetcher.fetch_batch(records)

    assert errors[0]["fetch_status"] == "fetch_error"


def test_mixed_results_split_correctly(tmp_path, fetcher):
    urls = ["https://example.com/ok", "https://example.com/fail"]
    records = _make_records(tmp_path, urls)
    crawl_results = [
        _make_crawl_result(urls[0], success=True, markdown="Good content here for testing purposes"),
        _make_crawl_result(urls[1], success=False, error="404"),
    ]

    with patch.dict(sys.modules, _mock_sys_modules(crawl_results)):
        ok, errors = fetcher.fetch_batch(records)

    assert len(ok) == 1
    assert len(errors) == 1
    assert ok[0]["fetch_status"] == "ok"
    assert errors[0]["candidate_url"] == urls[1]


def test_empty_records_returns_empty_lists(fetcher):
    with patch.dict(sys.modules, _mock_sys_modules([])):
        ok, errors = fetcher.fetch_batch([])

    assert ok == []
    assert errors == []


# ---------------------------------------------------------------------------
# thin content
# ---------------------------------------------------------------------------

def test_thin_content_goes_to_errors_and_leaves_file_untouched(tmp_path, strict_fetcher):
    urls = ["https://example.com/thin"]
    records = _make_records(tmp_path, urls)
    md_path = Path(records[0]["markdown_path"])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("original static content", encoding="utf-8")

    thin_markdown = "only a few words here"  # well below 150
    crawl_results = [_make_crawl_result(urls[0], success=True, markdown=thin_markdown)]

    with patch.dict(sys.modules, _mock_sys_modules(crawl_results)):
        ok, errors = strict_fetcher.fetch_batch(records)

    assert ok == []
    assert len(errors) == 1
    assert errors[0]["fetch_status"] == "thin_content"
    assert errors[0]["word_count"] == 5
    assert md_path.read_text() == "original static content"


def test_content_at_threshold_is_accepted(tmp_path):
    fetcher = Crawl4AIFetcher(max_concurrent=1, min_word_count=5)
    urls = ["https://example.com/ok"]
    records = _make_records(tmp_path, urls)
    exactly_five = "one two three four five"
    crawl_results = [_make_crawl_result(urls[0], success=True, markdown=exactly_five)]

    with patch.dict(sys.modules, _mock_sys_modules(crawl_results)):
        ok, errors = fetcher.fetch_batch(records)

    assert len(ok) == 1
    assert errors == []


# ---------------------------------------------------------------------------
# arun_many batch exception
# ---------------------------------------------------------------------------

def test_arun_many_exception_returns_all_as_errors(tmp_path, fetcher):
    urls = ["https://example.com/a", "https://example.com/b"]
    records = _make_records(tmp_path, urls)

    with patch.dict(sys.modules, _mock_sys_modules([], arun_many_exc=RuntimeError("browser crashed"))):
        ok, errors = fetcher.fetch_batch(records)

    assert ok == []
    assert len(errors) == 2
    assert all(e["fetch_status"] == "fetch_error" for e in errors)
    assert all("browser crashed" in e["error"] for e in errors)
