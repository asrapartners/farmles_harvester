# URL Registry — Cross-Run URL Intelligence

The `UrlRegistry` is a SQLite-backed cross-run store (see `farmles_harvester/registry/`). It is client-agnostic — it knows nothing about the pipeline. This document describes how the pipeline wires into it.

The registry exists to answer three questions on every subsequent run:

1. **Is this URL worth processing at all?**
   The URL must pass two independent checks — failing either skips it:
   Both checks are combined in a single call: `should_process_url(registry.get(url), registry.get_source(source_url))` in [`registry/evaluation.py`](../../farmles_harvester/registry/evaluation.py), which returns an `EvalVerdict` with `should_process` and a list of reasons.

2. **Does this page require browser-based rendering?**
   Stage 04 records whether a page's content is available in the static HTML response or requires JavaScript execution (`render_type`):
   - `static_html` — content is available to the static pipeline
   - `dynamic_js` — page requires JS; flagged for a subsequent crawl4ai browser-based crawl pass
   - `unknown` — not yet determined

## Data model

The registry is a single SQLite file with three operational tables and one bookkeeping table.

```
┌─────────────────────────┐        ┌──────────────────┐
│          urls           │        │     sources      │
│─────────────────────────│        │──────────────────│
│ url (PK)                │        │ source_url (PK)  │
│ candidate_score/status/ │        │ relevance_label  │
│   strength/type         │  N   N │ relevance_score  │
│ last_outcome_class      │◄──────►│ keyword_hits     │
│ retry_posture           │        │ negative_hits    │
│ render_type             │        │ page_count       │
│ markdown_status/        │        │ first/last_seen  │
│   strength/word_count   │        └──────────────────┘
│ first/last_seen_at      │
└─────────────────────────┘
           ▲ ▲
           │ │  joined by
           │ │
    ┌──────────────┐      ┌──────────────┐
    │ url_sources  │      │     meta     │
    │──────────────│      │──────────────│
    │ url (FK)     │      │ key (PK)     │
    │ source_url   │      │ value        │
    └──────────────┘      └──────────────┘
```

- **`urls`** — one row per discovered URL. Accumulates candidate scoring, fetch outcome, render type, and markdown quality across runs. This is the primary cross-run state store.
- **`url_sources`** — many-to-many join between a URL and the source(s) it was discovered from. A URL found linked from two different source sites gets two rows here.
- **`sources`** — one row per source domain. Holds the relevance verdict written by stage 06 (`confirmed`, `likely`, `uncertain`, `low_confidence`).
- **`meta`** — key-value store for registry bookkeeping (schema version).

For the full field reference — valid values and what each field means — see [`url_state.md`](url_state.md).

---

## Lifecycle

`orchestrator/run_pipeline.py` owns the single registry instance for a run:

```python
registry = UrlRegistry(registry_path)
try:
    # ... run stages ...
finally:
    registry.close()
```

`registry_path` defaults to `<run_dir>/url_registry.db` but can be overridden via the `registry_db` parameter to `run_pipeline()` to share a registry across runs.

## Stage order and registry touchpoints

```
00  normalize_source_leads
01  validate_urls
02  discover_links          ← registry.get(url)          [read, fast mode]
03  score_candidate_urls
    ingest_urls             ← upsert_many, record_source  [write]
04  generate_markdown_pages ← registry.get_many(urls)     [read, fast mode]
    ingest_fetch_outcomes   ← record_outcome              [write]
    ingest_markdown_outcomes← record_markdown_outcome     [write]
05  strip_boilerplate_blocks
06  score_source_relevance
    ingest_source_relevance ← upsert_source_many          [write]
```

## Reads (fast mode)

Two stages accept an optional `registry` kwarg. When provided, they query the registry to skip work already done in a prior run:

- **`stages/discover_links.py`** — calls `registry.get(url)` to check whether a discovered URL is already known, enabling fast-mode skipping.
- **`stages/generate_markdown_pages.py`** — calls `registry.get_many(urls)` to retrieve prior fetch state for candidate URLs.

Both stages operate normally without a registry (registry defaults to `None`).

## Writes (registry_ingest.py)

All writes go through `orchestrator/registry_ingest.py`. The four helpers are called by `run_pipeline.py` via `_safe_ingest()`, which swallows exceptions so a registry write failure never aborts the run.

| Helper | Registry methods | Called after |
|---|---|---|
| `ingest_urls()` | `upsert_many`, `record_source` | stage 03 (score_candidate_urls) |
| `ingest_fetch_outcomes()` | `record_outcome` | stage 04 (generate_markdown_pages) |
| `ingest_markdown_outcomes()` | `record_markdown_outcome` | stage 04 (generate_markdown_pages) |
| `ingest_source_relevance()` | `upsert_source_many` | stage 06 (score_source_relevance) |
