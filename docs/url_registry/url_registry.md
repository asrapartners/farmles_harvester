# URL Registry — Cross-Run URL Intelligence

The `UrlRegistry` is a SQLite-backed cross-run store (see `farmles_harvester/registry/`). It is client-agnostic — it knows nothing about the pipeline. This document describes how the pipeline wires into it.

The registry exists to answer three questions on every subsequent run:

> **Staleness:** Registry state can become stale — a misclassified URL or source will be skipped indefinitely. Running with `fast_mode: false` clears both cases. See [`fast_mode.md`](fast_mode.md) for details.

1. **Is this URL worth processing at all?**
   The URL must pass two independent checks — failing either skips it:
   Both checks are combined in a single call: `should_process_url(registry.get(url), registry.get_source(source_url))`, which returns an `EvalVerdict` with `should_process` and a list of reasons.

2. **Does this page require browser-based rendering?**
   The registry records whether a page's content is available in the static HTML response or requires JavaScript execution (`render_type`):
   - `static_html` — content is available via static fetch
   - `dynamic_js` — page requires JS; flagged for a subsequent crawl4ai browser-based crawl pass (see [`dynamic_pipeline/overview.md`](../dynamic_pipeline/overview.md))
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
- **`sources`** — one row per source domain. Holds the relevance verdict (`confirmed`, `likely`, `uncertain`, `low_confidence`).
- **`meta`** — key-value store for registry bookkeeping (schema version).

For the full field reference — valid values and what each field means — see [`url_state.md`](url_state.md).

For how the pipeline opens, reads, and writes the registry across stages — see [`pipeline_wiring.md`](pipeline_wiring.md).
