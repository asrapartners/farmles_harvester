# crawl4ai Fetcher

Source: [`farmles_harvester/web/crawl4ai_fetcher.py`](../../farmles_harvester/web/crawl4ai_fetcher.py)

`Crawl4AIFetcher` is the only component in the project that calls the crawl4ai library. Its job is narrow: accept a batch of URL records, browser-fetch them concurrently, and return two lists — successful results and error records. Everything else (writing markdown to disk, updating the registry, producing JSONL artifacts) is the harness's responsibility in [`run_dynamic_pipeline()`](../../farmles_harvester/orchestrator/run_dynamic_pipeline.py).

---

## crawl4ai components used

| Component | Role |
|-----------|------|
| `AsyncWebCrawler` | Manages the browser pool. `arun_many()` runs all URLs concurrently up to `max_concurrent`. |
| `BrowserConfig` | Sets `headless=True` — no GUI, suitable for server/CI execution. |
| `CrawlerRunConfig` | Per-run settings applied to every URL in the batch (see configuration below). |
| `CacheMode.BYPASS` | Skips crawl4ai's own on-disk cache. The registry and JSONL artifacts serve as the cache for this project. |
| `PruningContentFilter` | Drops low-signal HTML blocks before markdown conversion. Equivalent to what stage 05 (`strip_boilerplate_blocks`) does for statically fetched pages. |
| `DefaultMarkdownGenerator` | Converts the pruned HTML to markdown. Wired with the `PruningContentFilter` as its content filter. |

---

## Configuration

```python
Crawl4AIFetcher(
    max_concurrent=5,   # browser tabs open simultaneously
    use_cache=False,    # always bypasses crawl4ai cache
    min_word_count=150, # fetches below this are "thin" and treated as errors
)
```

**`CrawlerRunConfig` settings applied per URL:**

| Setting | Value | Why |
|---------|-------|-----|
| `page_timeout` | 60 000 ms | JS-heavy pages can be slow; 60 s balances coverage vs. hang risk. |
| `wait_for` | `js:() => document.body.innerText.length > 500` | Waits for meaningful text to appear before extraction, avoiding premature captures of loading states. |
| `remove_overlay_elements` | `True` | Removes cookie banners and modal overlays that pollute extracted content. |
| `cache_mode` | `CacheMode.BYPASS` | Ensures fresh fetches; staleness is managed by the registry, not crawl4ai. |

**`PruningContentFilter` settings:**

| Setting | Value | Why |
|---------|-------|-----|
| `threshold` | 0.4 | Blocks scoring below this are dropped. Calibrated to remove nav/header/footer chrome. |
| `threshold_type` | `"fixed"` | Applies the threshold as an absolute score, not relative to the page's score distribution. |

---

## Input / output contract

**Input** — list of record dicts, one per URL:

```json
{
  "candidate_url": "https://example.com/markets",
  "source_slug": "example-com",
  "markdown_path": "/abs/path/to/generated_wiki/sources/example-com/markets.md"
}
```

**Output** — a tuple `(ok_results, error_records)`.

`ok_results` — one dict per successfully fetched URL:

```json
{
  "candidate_url": "https://example.com/markets",
  "source_slug": "example-com",
  "markdown_path": "/abs/path/to/generated_wiki/sources/example-com/markets.md",
  "fetch_status": "ok",
  "word_count": 412,
  "bytes_before": 1024,
  "bytes_after": 3180,
  "bytes_incr_pcnt": 210.5
}
```

`error_records` — one dict per failed URL, with `fetch_status` indicating the failure mode:

| `fetch_status` | Cause |
|----------------|-------|
| `"thin_content"` | Fetch succeeded but word count was below `min_word_count` (default 150). |
| `"fetch_error"` | crawl4ai returned a failed result (non-success status). |
| `"timeout"` | Page did not satisfy the JS wait condition within `page_timeout`. |

Error records include an `"error"` field with a short description.

---

## Exception recovery

If `fetch_batch()` raises an unhandled exception, `run_dynamic_pipeline()` converts all input records to error records rather than letting the stage crash. This matches the harness pattern used across all pipeline stages — a partial failure does not abort the run. See [`run_dynamic_pipeline.py`](../../farmles_harvester/orchestrator/run_dynamic_pipeline.py) for the try/except block.

---

## Testability

The harness accepts an optional `fetcher=` parameter, which tests use to inject a `FakeCrawl4AIFetcher` without launching a real browser. See [`tests/harness/test_dynamic_pipeline_stage.py`](../../tests/harness/test_dynamic_pipeline_stage.py) for the full test suite covering happy-path, thin-content, and exception-recovery scenarios.
