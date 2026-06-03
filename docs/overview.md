# System Overview

Farmles Harvester discovers and harvests content from farmers market websites. Given a list of seed URLs it crawls each source, scores candidate pages, converts content to markdown, and classifies each source as a genuine farmers market or a false positive.

The system runs in two sequential pipelines. The static pipeline does the bulk of the work. The dynamic pipeline handles pages the static pipeline cannot access.

---

## Static pipeline

Runs first. Processes seed URLs through seven stages in sequence, passing data between stages as JSONL files on disk.

```
seed_urls.txt
    │
    ▼
00  Normalize source leads    — validate and normalise input URLs
01  Validate URLs             — check reachability and content type
02  Discover links            — BFS crawl to find candidate pages
03  Score candidate URLs      — rank candidates by relevance signal
04  Generate markdown pages   — fetch and convert HTML to markdown
05  Strip boilerplate blocks  — remove repeated nav/footer chrome
06  Score source relevance    — classify each source as a farmers market
    │
    ▼
generated_wiki/sources/<slug>/
```

Output: a wiki folder per source containing markdown pages and `source_metadata.json`. See [`static_pipeline/`](static_pipeline/) for per-stage detail and [`01_orchestrator_design.md`](01_orchestrator_design.md) for the orchestrator design.

---

## Dynamic pipeline

Runs after the static pipeline completes. Handles pages that require JavaScript execution — pages the static HTTP fetch returned empty or boilerplate-only content for.

The static pipeline flags these as `render_type = dynamic_js` in the registry. The orchestrator queries all such entries and passes the full batch to the dynamic pipeline, which uses crawl4ai's async browser crawler to fetch them.

```
url_registry.db  (render_type = dynamic_js)
    │
    ▼
orchestrator builds batch  (url + md_path per entry)
    │
    ▼
Browser fetch (crawl4ai)  →  Strip boilerplate  →  Update registry
    │
    ▼
generated_wiki/sources/<slug>/   (same paths, richer content)
```

Output overwrites the thin or empty markdown left by the static pipeline at the same paths. Downstream consumers see no difference. See [`dynamic_pipeline/overview.md`](dynamic_pipeline/overview.md) for design detail.

---

## Registry as the handoff

The URL registry (`url_registry.db`) is the shared state between the two pipelines. The static pipeline writes what it learns — candidate scores, fetch outcomes, render types, markdown quality — and the dynamic pipeline reads that state to know what work is left.

See [`url_registry/`](url_registry/) for the registry data model, field reference, and fast-mode behaviour.
