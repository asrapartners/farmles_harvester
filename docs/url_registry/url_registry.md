# URL Registry — Cross-Run URL Intelligence

The `UrlRegistry` is a SQLite-backed cross-run store (see `farmles_harvester/registry/`). It is client-agnostic — it knows nothing about who calls it or how results are used.

The registry exposes two kinds of queries to callers:

1. **Should this URL be processed?**
   Combined filter across URL history and source quality: `should_process_url(registry.get(url), registry.get_source(source_url))` returns an `EvalVerdict(should_process, reasons)`. See [`url_state.md`](url_state.md) for the fields that drive this decision.

2. **What is the render type of this URL?**
   `registry.get(url)["render_type"]` returns `static_html`, `dynamic_js`, or `unknown`. The registry stores what was observed — the caller decides what to do with it.

> **Staleness:** Registry state can become stale — a misclassified URL or source is skipped indefinitely until the state is refreshed. See [`static_pipeline/fast_mode.md`](../static_pipeline/fast_mode.md) for the reset mechanism.

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
- **`sources`** — one row per source domain. Holds the relevance verdict (`confirmed`, `likely`, `uncertain`, `low_confidence`).
- **`meta`** — key-value store for registry bookkeeping (schema version).

For the full field reference — valid values and what each field means — see [`url_state.md`](url_state.md).

For how the pipeline opens, reads, and writes the registry across stages — see [`static_pipeline/pipeline_wiring.md`](../static_pipeline/pipeline_wiring.md).
