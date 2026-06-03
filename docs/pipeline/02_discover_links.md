# Discover Links Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

Stage `02 — discover_links` fetches each validated source page and extracts all links found in `<a href>` tags. It does not decide which links are useful, extract facts, or crawl beyond the source page.

---

## Artifacts

Consumes: `01_validated_sources.jsonl`
Produces: `02_discovered_links.jsonl`, `02_discovered_links_summary.json`, `02_discovered_links_errors.jsonl`

Registry input (fast mode only): `urls.candidate_strength` — written by stage 03 after each run; used on the next run to skip BFS links already known to be weak.

---

## Input Filtering

Process only records where:
- `validation_status` is `valid` or `redirected`
- `content_type` starts with `text/html` or `application/xhtml+xml`
- `final_url` is not null

Skipped records are counted in the summary, not written as errors.

---

## Link Extraction

For each `<a href>` on the source page:

1. Read `raw_href` and `link_text`.
2. Ignore: empty hrefs, `#fragment`-only, `javascript:`, `mailto:`, `tel:`.
3. Resolve relative hrefs against the source page URL.
4. Lightly normalize the resulting absolute URL.
5. Classify as internal or external (same registered domain; `www` treated as equivalent).
6. External links are recorded with `follow_allowed = false` and not followed.
7. Deduplicate per source page — if the same URL appears twice, keep the first non-empty link text.

---

## BFS and Fast Mode

By default (`max_depth = 1`) only the seed source page is fetched. When `max_depth > 1` the stage queues internal links for follow-up fetches (BFS). Two independent pruning layers control which links enter the queue.

### Layer 1 — current-run score (always active)

Before queuing any internal link, stage 02 calls `score_discovered_link()` on it. Links below `follow_threshold` (default 40) are not queued. This prunes weak links immediately, without fetching them, based on URL tokens and link text alone.

### Layer 2 — prior-run strength (fast mode only)

`fast_mode = true` adds a second gate using the registry. After each run, stage 03 writes `candidate_strength` into `urls.candidate_strength`. On the next run, stage 02 reads that value via `registry.get(discovered_url)` and skips links already known to be weak:

| `urls.candidate_strength` | result |
|---|---|
| row not found (new URL) | queued — always processed |
| `"strong"` | queued |
| `"medium"` | skipped |
| `"weak"` | skipped |
| field is `NULL` on existing row | skipped |

The minimum passing strength is `fast_url_min_strength` (default `"strong"`). Permanent failures (`retry_posture = "permanent"`) are also skipped regardless of strength (`fast_skip_permanent_failures`, default `true`).

> **Edge case:** a URL in the registry with no `candidate_strength` set (e.g. inserted before stage 03 ever ran) gets rank −1 and is silently skipped in fast mode. If a URL is unexpectedly absent from BFS output, check its `candidate_strength` in the registry.

---

## Output Record Contract

Required fields:

```text
run_id
source_lead_id
source_url
raw_href
discovered_url
link_text
is_internal
follow_allowed
depth
discovery_method
discovered_at
```

Optional: `source_domain`, `discovered_domain`, `input_url`, `normalized_url`

Example:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000001",
  "source_url": "https://www.apexfarmersmarket.com/",
  "source_domain": "apexfarmersmarket.com",
  "raw_href": "/vendors",
  "discovered_url": "https://www.apexfarmersmarket.com/vendors",
  "discovered_domain": "apexfarmersmarket.com",
  "link_text": "Vendors",
  "is_internal": true,
  "follow_allowed": true,
  "depth": 1,
  "discovery_method": "html_anchor",
  "discovered_at": "2026-05-16T11:45:00Z"
}
```

---

## Error Artifact Contract

`02_discovered_links_errors.jsonl` — for unexpected processing failures (not filtered hrefs).

Required fields: `run_id`, `stage_name`, `source_lead_id`, `source_url`, `error_type`, `message`, `retryable`, `created_at`

Network failures fetching a source page produce an error record. Filtered hrefs (`mailto:`, `tel:`, empty, fragment) are counted in the summary, not written as errors.

---

## Summary Artifact Contract

`02_discovered_links_summary.json` — required fields:

```text
stage_name
stage_number
run_id
input_records
processed_sources
skipped_sources
source_fetch_errors
output_records
internal_links
external_links
error_records
capped_sources
fast_skipped
started_at
completed_at
```

---

## Implementation

**Entry function:** `run_discover_links(input_path, stage_paths, run_id, config, fetcher, registry)`
[`stages/discover_links.py`](../../farmles_harvester/stages/discover_links.py)

Call sequence:
1. `stream_jsonl()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — streams validated source records
2. `fetcher.fetch(final_url)` — [`web/fetcher.py`](../../farmles_harvester/web/fetcher.py) — fetches the source page
3. `extract_links_from_html()` — [`web/html_utils.py`](../../farmles_harvester/web/html_utils.py) — extracts `<a href>` links
4. `normalize_url()` / `is_internal_link()` — [`web/url_utils.py`](../../farmles_harvester/web/url_utils.py) — normalizes and classifies each link
5. `score_discovered_link()` — [`stages/score_candidate_urls.py`](../../farmles_harvester/stages/score_candidate_urls.py) — pre-scores links during discovery (fast mode BFS gate)
6. `evaluate_url_strength()` — [`registry/evaluation.py`](../../farmles_harvester/registry/evaluation.py) — registry-based skip decision (fast mode only)
7. `JsonlWriter` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — writes output artifact

Input field contract: `VALIDATED_SOURCE_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)

---

## Configuration

```json
{
  "max_depth": 1,
  "follow_threshold": 40,
  "per_source_follow_cap": 200,
  "fast_mode": false,
  "fast_url_min_strength": "strong",
  "fast_skip_permanent_failures": true,
  "timeout_seconds": 15,
  "user_agent": "FarmlessBot/0.1",
  "record_external_links": true
}
```

---

## Definition of Done

1. Reads `01_validated_sources.jsonl`; processes only valid HTML records.
2. Fetches each processable source URL.
3. Extracts and normalizes `<a href>` links; ignores non-web hrefs.
4. Classifies links as internal or external; deduplicates per source page.
5. Applies BFS follow logic: score threshold, per-source cap, optional fast-mode registry gate on `urls.candidate_strength`.
6. Writes `02_discovered_links.jsonl`, `02_discovered_links_summary.json`, `02_discovered_links_errors.jsonl`.
7. Returns a JSON-serializable `StageResult`.
8. Does not score links, fetch discovered links, extract facts, convert markdown, follow external links, or update the manifest.
