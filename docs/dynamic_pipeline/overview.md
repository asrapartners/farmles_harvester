# Dynamic Pipeline — Browser-Based Crawl

The static pipeline fetches pages with a plain HTTP request. Pages that require JavaScript to render their content return empty or boilerplate-only markdown — the registry flags these as `render_type = dynamic_js`. The dynamic pipeline handles those pages using a browser-based crawl via crawl4ai.

**This directory:**
- `overview.md` — orchestrator handoff, data flow, and the harness/fetcher layer diagram (this file)
- [`crawl4ai_fetcher.md`](crawl4ai_fetcher.md) — crawl4ai components, configuration choices, and input/output contract

For the system-level view of both pipelines, see [`overview.md`](../overview.md).

---

## Architecture

The dynamic pipeline has two distinct layers. The harness owns all pipeline concerns (artifact I/O, registry updates, error routing). The crawl4ai wrapper owns only the browser fetch.

```
                         run_pipeline.py
                               │
                    dynamic_candidates.jsonl
                               │
                               ▼
               ┌─────────────────────────────────────┐
               │           Pipeline harness          │
               │      run_dynamic_pipeline()         │
               │  orchestrator/run_dynamic_pipeline.py│
               │                                     │
               │  • reads JSONL records              │
               │  • routes ok / error results        │
               │  • writes markdown to disk          │
               │  • updates registry                 │
               │  • produces d01 artifacts           │
               └──────────────┬──────────────────────┘
                              │  fetch_batch(records)
                              │
                              ▼
               ┌─────────────────────────────────────┐
               │          crawl4ai wrapper            │
               │         Crawl4AIFetcher              │
               │       web/crawl4ai_fetcher.py        │
               │                                     │
               │  • launches headless browser        │
               │  • runs AsyncWebCrawler.arun_many() │
               │  • applies PruningContentFilter     │
               │  • returns (ok_results, errors)     │
               └─────────────────────────────────────┘
```

See [`crawl4ai_fetcher.md`](crawl4ai_fetcher.md) for what each crawl4ai component does and why it is configured the way it is.

---

## Orchestrator handoff

After the static pipeline completes, the orchestrator ([`run_pipeline.py`](../../farmles_harvester/orchestrator/run_pipeline.py)) mines `05_stripped_pages.jsonl` — the final stage artifact — and filters for records where `render_type = dynamic_js`. It writes those records to `dynamic_candidates.jsonl` in the run directory and passes that file as the input to [`run_dynamic_pipeline()`](../../farmles_harvester/orchestrator/run_dynamic_pipeline.py).

```python
run_pipeline(...)           # static pipeline completes

dynamic_candidates = [
    r for r in read_jsonl(paths_05.output_path)
    if r.get("render_type") == "dynamic_js"
]
write_jsonl(dynamic_candidates_path, dynamic_candidates)
run_dynamic_pipeline(input_path=dynamic_candidates_path, run_dir=run_dir, registry=registry)
```

Each record already carries `candidate_url`, `source_slug`, and `markdown_path` from stage 04. The dynamic pipeline receives a fully resolved, inspectable file — no registry query, no path computation needed.

---

## What the dynamic pipeline does

The dynamic pipeline is intentionally lean. The static pipeline already decided which URLs are worth crawling and where their output goes. The dynamic pipeline only needs to:

1. **Browser-fetch** — pass the full batch of URLs to [`Crawl4AIFetcher.fetch_batch()`](../../farmles_harvester/web/crawl4ai_fetcher.py) in a single call. Browser startup cost is amortised across all URLs.
2. **Strip boilerplate** — crawl4ai's `PruningContentFilter` handles this during markdown generation, equivalent to what stage 05 does for static pages.
3. **Update registry** — refresh `markdown_status`, `markdown_word_count`, and `markdown_strength` for each fetched URL.

No normalisation, no link discovery, no scoring.

---

## Output

The dynamic pipeline writes markdown to the same `md_path` the static pipeline recorded in `source_metadata.json` and the registry, overwriting any thin or empty content left by the static fetch. Downstream consumers (relevance scoring, the report CLI) see no difference — they find richer content at the same path.

The registry update is the critical step: `markdown_status`, `markdown_word_count`, and `markdown_strength` must be refreshed so future fast-mode decisions reflect the browser-fetched quality rather than the stale static attempt.

**Artifacts produced** (in the run directory):

| File | Contents |
|------|----------|
| `d01_browser_fetched_pages.jsonl` | One record per successful fetch |
| `d01_browser_fetched_pages_errors.jsonl` | Timeout, thin-content, and fetch-error records |
| `d01_browser_fetched_pages_summary.json` | Aggregated counts |

---

## Staleness

The same fast-mode staleness rules apply to the dynamic pipeline as to the static pipeline. See [`static_pipeline/fast_mode.md`](../static_pipeline/fast_mode.md).
