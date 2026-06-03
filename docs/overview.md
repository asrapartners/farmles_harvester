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

The orchestrator reads `05_stripped_pages.jsonl` and filters for records where `render_type = dynamic_js`. It writes those to `dynamic_candidates.jsonl` and passes that file as input to the dynamic pipeline.

```
05_stripped_pages.jsonl  (render_type = dynamic_js entries)
    │
    ▼  orchestrator filters → dynamic_candidates.jsonl
    │
    ▼
Browser fetch (crawl4ai)  →  Strip boilerplate  →  Update registry
    │
    ▼
generated_wiki/sources/<slug>/   (same paths, richer content)
```

Output overwrites the thin or empty markdown left by the static pipeline at the same paths. Downstream consumers see no difference. See [`dynamic_pipeline/overview.md`](dynamic_pipeline/overview.md) for design detail.

---

## Registry

The URL registry (`url_registry.db`) accumulates what the static pipeline learns across runs — candidate scores, fetch outcomes, render types, markdown quality. It drives two decisions on each run: whether a URL is worth processing, and what render method it requires. It is not the handoff mechanism between pipelines; that is file-based.

See [`url_registry/`](url_registry/) for the registry data model and field reference.
