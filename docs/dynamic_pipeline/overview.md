# Dynamic Pipeline — Browser-Based Crawl

For the system-level view of how the static and dynamic pipelines relate, see [`overview.md`](../overview.md).

---

## Orchestrator handoff

After the static pipeline completes, the orchestrator queries the registry for all pages flagged as dynamic and not yet successfully fetched:

```python
run_pipeline(...)           # static pipeline completes

dynamic_candidates = registry.query(
    where="render_type = 'dynamic_js' AND markdown_status = 'not_attempted'"
)
run_dynamic_pipeline(candidates=dynamic_candidates, run_dir=run_dir, registry=registry)
```

Each candidate carries the URL and the `md_path` already assigned by the static pipeline. The dynamic pipeline receives a fully resolved batch — no path computation needed.

---

## What the dynamic pipeline does

The dynamic pipeline is intentionally lean. The static pipeline already decided which URLs are worth crawling and where their output goes. The dynamic pipeline only needs to:

1. **Browser-fetch** — pass the full batch of URLs to crawl4ai's async crawler in a single call. Browser startup cost is amortised across all URLs.
2. **Strip boilerplate** — apply the same boilerplate removal as stage 05 of the static pipeline.
3. **Update registry** — refresh `markdown_status`, `markdown_word_count`, and `markdown_strength` for each fetched URL.

No normalisation, no link discovery, no scoring.

---

## Output

The dynamic pipeline writes markdown to the same `md_path` the static pipeline recorded in `source_metadata.json` and the registry, overwriting any thin or empty content left by the static fetch. Downstream consumers (relevance scoring, the report CLI) see no difference — they find richer content at the same path.

The registry update is the critical step: `markdown_status`, `markdown_word_count`, and `markdown_strength` must be refreshed so future fast-mode decisions reflect the browser-fetched quality rather than the stale static attempt.

---

## Staleness

The same fast-mode staleness rules apply. If a page was browser-fetched in a prior run and produced sufficient markdown (`markdown_strength = strong`), the dynamic pipeline can skip it on the next run. Running with `fast_mode: false` forces a full re-fetch in both pipelines. See [`url_registry/fast_mode.md`](../url_registry/fast_mode.md).
