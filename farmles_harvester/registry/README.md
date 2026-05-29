# URL Registry

SQLite-backed cross-run store for discovered URLs, their fetch outcomes, and the source pages they came from.

## Data model

### `urls`
One row per discovered candidate URL. Tracks scoring, fetch outcomes, render type, and markdown generation status. `first_seen_at` is immutable after insert; everything else is updated on each run.

Key columns:
- `candidate_score / status / strength / type` — set by the scoring stage
- `last_outcome_class` — one of the `OUTCOME_CLASSES` constants (e.g. `ok`, `http_5xx`, `dns_error`)
- `retry_posture` — `permanent`, `transient`, or `unknown`; `NULL` when outcome is `ok` or not yet fetched
- `render_type` — `static_html`, `dynamic_js`, or `unknown`
- `markdown_status` — `not_attempted`, `generated`, `empty`, or `boilerplate_only`
- `times_seen` — increments on every upsert, regardless of outcome

### `url_sources`
Junction table: every (url, source_url) pair observed. A URL can be found on multiple source pages across runs.

### `sources`
One row per source page. Stores relevance scoring metadata: `relevance_label`, `relevance_score`, `keyword_hits`, `negative_hits`, `total_word_count`, `page_count`. Answers "how good was this source page as a harvest site?" independently of what URLs it yielded.

### `meta`
Key/value store for registry metadata (e.g. `schema_version`).

## Typical call sequence

```python
with UrlRegistry("path/to/registry.sqlite") as reg:
    # 1. Register discovered URLs (from discover_links output)
    reg.upsert_many(rows, run_id=run_id)
    # rows: list of dicts with keys: url, source_url, and optionally
    # candidate_score, candidate_status, candidate_strength, candidate_type

    # 2. Record fetch outcome
    reg.record_outcome(url, outcome_class="ok", retry_posture=None, detail=None, run_id=run_id)
    reg.record_outcome(url, outcome_class="http_5xx", retry_posture="transient", detail={"status": 503}, run_id=run_id)

    # 3. Record render type (after dynamic JS detection)
    reg.set_render_type(url, "dynamic_js", evidence={"marker": "next_data"})

    # 4. Record markdown generation result
    reg.record_markdown_outcome(url, status="generated", word_count=1200, path="sources/foo.md", run_id=run_id)

    # 5. Update source page relevance
    reg.upsert_source(source_url, relevance_label="confirmed", relevance_score=310, run_id=run_id)
```

## Reading

```python
reg.get(url)                          # single URL dict or None
reg.get_many(urls)                    # {url: dict}
reg.contains(url)                     # bool
reg.contains_many(urls)               # {url: bool}
reg.query(where="candidate_score >= ?", params=(70,), order_by="candidate_score", limit=100)
reg.count(where="last_outcome_class = ?", params=("ok",))

reg.sources_of(url)                   # iterator of source_urls for a given url
reg.urls_from(source_url)             # iterator of urls discovered from a given source
reg.get_source(source_url)            # source row dict or None
```

## Allowed values

```python
OUTCOME_CLASSES   # ok, policy_rejected, dns_error, tls_error, connect_error,
                  # timeout, http_4xx, http_5xx, rate_limited, redirect_loop,
                  # blocked, soft_404, wrong_content_type, empty, parked,
                  # boilerplate_only, size_exceeded
RETRY_POSTURES    # permanent, transient, unknown
RENDER_TYPES      # static_html, dynamic_js, unknown
MARKDOWN_STATUSES # generated, empty, boilerplate_only, not_attempted
```

All constants are importable from `farmles_harvester.registry`.

## Notes

- The schema is applied idempotently on every `UrlRegistry` open — safe to reopen existing databases.
- `upsert_many` wraps all rows in a single transaction. Use it over repeated `upsert` calls for bulk inserts.
- `record_outcome` enforces the `retry_posture` constraint at the Python level before hitting the DB check constraint.
