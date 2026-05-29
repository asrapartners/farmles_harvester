# Example flow: DNS_PROBE_FINISHED_NXDOMAIN

Traces what happens when a URL's domain does not resolve (NXDOMAIN). Two scenarios are covered: the error occurring on a **seed/source URL** (stage 01) and on a **discovered candidate URL** (stage 04).

---

## Scenario A: NXDOMAIN on a seed URL

The broken domain appears in the seed file, e.g. `https://dead-source.com/`.

### Stage 01 — validate_urls
`fetcher.fetch("https://dead-source.com/")` raises a network exception (e.g. `socket.gaierror` or a browser-level DNS error).

Caught by the generic `except Exception as exc` branch. Written to `01_validated_sources/output.jsonl`:
```json
{
  "normalized_url": "https://dead-source.com/",
  "validation_status": "fetch_error",
  "http_status": null,
  "failure_reason": "DNS_PROBE_FINISHED_NXDOMAIN (or socket.gaierror message)"
}
```

### ingest_validation_failures (after stage 01)
`ingest_validation_failures()` finds the `fetch_error` record and calls:
1. `registry.upsert({"url": "https://dead-source.com/"}, ...)` — creates the registry row
2. `registry.record_outcome(..., outcome_class="connect_error", retry_posture="permanent", detail="DNS_PROBE_FINISHED_NXDOMAIN", ...)`

Registry row:
```
url:                  https://dead-source.com/
last_outcome_class:   connect_error
retry_posture:        permanent
consecutive_failures: 1
last_error_at:        <timestamp>
```

### Stage 02 — discover_links
`_is_processable()` returns `False` — `validation_status` is not `"valid"` or `"redirected"`.
The record is counted as `skipped_sources`. No fetch is attempted, no links are discovered.

### Stages 03–06
No output exists for this seed, so nothing flows through scoring, markdown generation, or relevance scoring.

### On the next run (fast mode)
The registry entry is already present with `retry_posture: "permanent"`. If `fast_skip_permanent_failures` is enabled, `evaluate_url_strength()` will signal `should_process: False` for this URL, preventing redundant retries.

---

## Scenario B: NXDOMAIN on a discovered candidate URL

A valid source page links to `https://dead-product.com/item`, which does not resolve.

### Stage 01 — validate_urls
Source page passes with `validation_status: "valid"`. Proceeds normally.

### Stage 02 — discover_links
Source page is fetched successfully. `https://dead-product.com/item` is found as a link and written to `02_discovered_links/output.jsonl`. The broken domain is not fetched here — discovery only follows **internal** links for BFS. External links are recorded as-is.

### Stage 03 — score_candidate_urls
`https://dead-product.com/item` is scored. Assuming it passes the threshold, it appears in `03_candidate_urls/output.jsonl` with `candidate_status: "selected"`.

### ingest_urls (after stage 03)
`ingest_urls()` calls `registry.upsert_many()`. The URL enters the registry for the first time:
```
url:                https://dead-product.com/item
last_outcome_class: NULL
retry_posture:      NULL
times_seen:         1
```

### Stage 04 — generate_markdown_pages
`fetcher.fetch("https://dead-product.com/item")` raises an exception. Caught by `except Exception as e` with `error_type = "fetch_error"`. Written to `04_markdown_pages/output.jsonl`:
```json
{
  "candidate_url": "https://dead-product.com/item",
  "fetch_status": "fetch_error"
}
```

### ingest_fetch_outcomes (after stage 04)
`ingest_fetch_outcomes()` maps `fetch_status: "fetch_error"` → `outcome_class: "connect_error"`, `retry_posture: "transient"`.

Registry row is updated:
```
url:                  https://dead-product.com/item
last_outcome_class:   connect_error
retry_posture:        transient
consecutive_failures: 1
last_error_at:        <timestamp>
```

### Stages 05–06
Strip boilerplate and source relevance scoring operate on the markdown output from stage 04. Since no markdown was produced for this URL, it does not appear in those stages.

### On the next run (fast mode)
`discover_links` calls `registry.get("https://dead-product.com/item")`. `evaluate_url_strength()` sees `retry_posture: "transient"` and `consecutive_failures: 1`. A `transient` failure is **not** skipped — the URL will be retried.

If the domain remains unresolvable across multiple runs, `consecutive_failures` keeps incrementing. The retry posture remains `transient` until manually updated or until a future stage detects repeated NXDOMAIN and promotes it to `permanent`.
