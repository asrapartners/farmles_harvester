# Discover Links Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

Stage `02 — discover_links` fetches each validated source page and extracts all links found in `<a href>` tags. It does not decide which links are useful, extract facts, or crawl beyond the source page.

---

## Artifacts

Consumes: `01_validated_sources.jsonl`
Produces: `02_discovered_links.jsonl`, `02_discovered_links_summary.json`, `02_discovered_links_errors.jsonl`

Registry input (fast mode only): `urls.candidate_strength` — written by stage 03 after each run; used on the next run to skip BFS links already known to be weak.

Fields read from each input record ([`stages/discover_links.py`](../../farmles_harvester/stages/discover_links.py), `VALIDATED_SOURCE_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)):

| Field | Required | How this stage uses it |
|---|---|---|
| `final_url` | yes | URL to fetch and seed the BFS queue |
| `source_lead_id` | yes | Tags all output records; key for per-source BFS cap tracking |
| `validation_status` | yes | Filtered — only `valid` or `redirected` records are processed |
| `normalized_url` | yes | Validated; passed through to output records |
| `content_type` | no | Filtered — must start with `text/html` or `application/xhtml+xml`; absent = skipped |
| `input_url` | no | Passed through to output records if present |
| `run_id` | yes | Validated; output re-injects it from the harness `run_id` arg |
| all other fields | — | Ignored |

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

Each line in `02_discovered_links.jsonl` is one JSON object.

| Field | Required | Description |
|---|---|---|
| `run_id` | yes | Run identifier, injected by the harness |
| `source_lead_id` | yes | Identity of the seed lead; preserved from input |
| `source_url` | yes | Original seed URL (not the BFS fetch URL) |
| `raw_href` | yes | Unresolved href value from the `<a>` tag |
| `discovered_url` | yes | Resolved and normalized absolute URL |
| `link_text` | yes | Anchor text of the link |
| `is_internal` | yes | True if `discovered_url` is on the same registered domain as `source_url` |
| `follow_allowed` | yes | Same as `is_internal`; external links are always `false` |
| `depth` | yes | BFS depth at which this link was discovered (1 = source page) |
| `discovery_method` | yes | Always `html_anchor` |
| `discovered_at` | yes | ISO-8601 timestamp |
| `source_domain` | no | Registered domain of `source_url` |
| `discovered_domain` | no | Registered domain of `discovered_url` |
| `input_url` | no | Passed through from input if present |
| `normalized_url` | no | Passed through from input if present |

---

## Error Artifact Contract

`02_discovered_links_errors.jsonl` — for unexpected processing failures (not filtered hrefs).

Required fields: `run_id`, `stage_name`, `source_lead_id`, `source_url`, `error_type`, `message`, `retryable`, `created_at`

Network failures fetching a source page produce an error record. Filtered hrefs (`mailto:`, `tel:`, empty, fragment) are counted in the summary, not written as errors.

---

## Summary Artifact Contract

`02_discovered_links_summary.json` — one JSON object written after the stage completes.

| Field | Description |
|---|---|
| `stage_name` | `discover_links` |
| `stage_number` | `02` |
| `run_id` | Run identifier |
| `input_records` | Total records read from `01_validated_sources.jsonl` |
| `processed_sources` | Source pages successfully fetched and parsed |
| `skipped_sources` | Records filtered out by input filtering rules |
| `source_fetch_errors` | Source pages that could not be fetched |
| `output_records` | Total link records written |
| `internal_links` | Links on the same domain as the source |
| `external_links` | Links on a different domain |
| `error_records` | Records written to the errors artifact |
| `max_depth_reached` | Highest BFS depth actually visited this run |
| `capped_sources` | Sources that hit `per_source_follow_cap` |
| `fast_skipped` | BFS links skipped by the registry fast-mode gate |
| `per_source_follow_cap` | Config value in effect for this run |
| `started_at` | ISO-8601 timestamp |
| `completed_at` | ISO-8601 timestamp |

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
6. Does not score links for selection, fetch discovered links, extract facts, convert markdown, follow external links, or update the manifest.
