# Registry Integration

The `UrlRegistry` is a SQLite-backed cross-run store (see `farmles_harvester/registry/`). It is client-agnostic — it knows nothing about the pipeline. This document describes how the pipeline wires into it.

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
