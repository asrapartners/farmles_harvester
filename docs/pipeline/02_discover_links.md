# Discover Links Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

The `discover_links` stage takes validated source records and discovers links present on each validated source page.

This stage answers:

> What links are present on this source page?

It does **not** decide which links are useful.  
It does **not** extract farmers market facts.  
It does **not** crawl the whole website.

For v1, this stage fetches only the validated source page, usually the homepage or final resolved URL, parses its HTML, and records links found in `<a href="...">...</a>` tags.

---

## Stage Name

```text
discover_links
```

## Stage Number

```text
02
```

---

## Position in Pipeline

```text
00_normalized_source_leads.jsonl
   ↓
01_validated_sources.jsonl
   ↓
02_discovered_links.jsonl
   ↓
03_candidate_pages.jsonl
```

---

## Consumed Artifact

```text
01_validated_sources.jsonl
```

Each input record represents one validated source URL.

Example input record:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000001",
  "input_url": "apexfarmersmarket.com",
  "normalized_url": "https://apexfarmersmarket.com/",
  "final_url": "https://www.apexfarmersmarket.com/",
  "domain": "apexfarmersmarket.com",
  "validation_status": "valid",
  "http_status": 200,
  "content_type": "text/html",
  "redirected": true,
  "redirect_chain": [
    "https://apexfarmersmarket.com/",
    "https://www.apexfarmersmarket.com/"
  ],
  "validated_at": "2026-05-16T11:35:00Z"
}
```

---

## Produced Artifacts

```text
02_discovered_links.jsonl
02_discovered_links_summary.json
02_discovered_links_errors.jsonl
```

---

## Core Responsibility

For each processable validated source record:

1. Read `final_url`.
2. Fetch the `final_url`.
3. Parse the HTML response body.
4. Extract links from `<a href="...">...</a>` tags.
5. Convert relative links into absolute URLs.
6. Lightly normalize discovered URLs.
7. Determine whether each discovered link is internal or external.
8. Deduplicate discovered links per source page.
9. Apply configured link caps.
10. Write discovered link records to `02_discovered_links.jsonl`.
11. Write structured errors to `02_discovered_links_errors.jsonl`.
12. Write stage summary to `02_discovered_links_summary.json`.
13. Return a serializable `StageResult`.

---

## Non-Responsibilities

This stage must not:

- score candidate pages
- extract market name
- extract market hours
- extract location
- extract vendors
- convert HTML to markdown
- call an LLM
- crawl the whole website
- fetch discovered links
- follow external domains
- decide final canonical market identity
- update `manifest.json` directly

---

## Input Filtering Rules

The stage should process only records where:

```text
validation_status in ["valid", "redirected"]
content_type contains "text/html" or "application/xhtml+xml"
final_url is not null
```

The stage should skip records where:

```text
validation_status in ["broken", "blocked", "timeout", "invalid_url", "fetch_error", "non_html"]
```

Skipped records are not errors. They should be counted in the summary.

---

## Fetch Policy

For v1, fetch only the source page represented by `final_url`.

Example:

```text
source final_url = https://examplemarket.org/
```

The stage may fetch:

```text
https://examplemarket.org/
```

The stage must not fetch discovered links such as:

```text
https://examplemarket.org/vendors
https://examplemarket.org/visit
https://examplemarket.org/calendar
```

Those pages are fetched by later stages.

---

## Link Extraction Rules

The stage should extract links from HTML anchor tags:

```html
<a href="/vendors">Our Vendors</a>
<a href="https://example.org/visit">Visit Us</a>
```

For each anchor tag:

1. Read the raw `href`.
2. Read the visible link text.
3. Ignore empty `href` values.
4. Ignore fragment-only links such as `#top`.
5. Ignore JavaScript links such as `javascript:void(0)`.
6. Ignore `mailto:` links for v1.
7. Ignore `tel:` links for v1.
8. Convert relative URLs to absolute URLs using the source page URL.

Example:

```text
source_url = https://examplemarket.org/
raw_href = /vendors

discovered_url = https://examplemarket.org/vendors
```

---

## Href Filtering vs URL Validation

This stage performs only lightweight href filtering.

It may reject or ignore hrefs that cannot become usable web-link candidates, such as:

```text
""
"#top"
"javascript:void(0)"
"mailto:info@example.org"
"tel:5551234567"
```

This stage does **not** perform network validation of discovered links.

A discovered URL may still later return:

```text
404
403
timeout
non_html
```

That belongs to a later validation or fetch stage.

Clean distinction:

```text
discover_links
= extract and normalize hrefs found in HTML
= reject obvious non-web / unparseable hrefs

validate/fetch later stage
= check whether discovered URLs actually work on the internet
```

---

## Internal vs External Link Rule

A link is internal if it belongs to the same registered domain as the source.

Example:

```text
source domain: examplemarket.org
discovered domain: examplemarket.org
is_internal: true
```

Treat `www` as equivalent:

```text
examplemarket.org
www.examplemarket.org
```

Different domain:

```text
source domain: examplemarket.org
discovered domain: facebook.com
is_internal: false
```

External links should be recorded but not followed.

---

## Follow Policy

For v1:

```text
internal link:
  record it
  follow_allowed = true

external link:
  record it
  follow_allowed = false
```

Important:

`follow_allowed = true` means a later stage is allowed to consider this URL for fetching.

It does not mean this stage should fetch the link.

---

## Deduplication Rule

Deduplicate discovered links per source page.

If the same discovered URL appears multiple times on the same source page, write only one record.

When duplicate links have different link text, keep the first non-empty link text.

Example:

```html
<a href="/vendors">Vendors</a>
<a href="/vendors">Our Vendors</a>
```

Output one record:

```json
{
  "discovered_url": "https://examplemarket.org/vendors",
  "link_text": "Vendors"
}
```

---

## Caps

To prevent one page from dominating the run, use these default caps:

```json
{
  "max_links_per_source_page": 500,
  "max_internal_links_per_source": 200,
  "max_external_links_per_source": 100
}
```

If caps are reached, the summary should record it.

Caps should be applied after obvious ignored hrefs are filtered and after URL normalization.

---

## Output Record Contract

Each line in `02_discovered_links.jsonl` must be one JSON object.

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

Optional fields:

```text
site_id
source_domain
discovered_domain
normalized_discovered_url
```

Example internal link record:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000001",
  "site_id": "site_8f31a2",
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

Example external link record:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000001",
  "site_id": "site_8f31a2",
  "source_url": "https://www.apexfarmersmarket.com/",
  "source_domain": "apexfarmersmarket.com",
  "raw_href": "https://www.facebook.com/apexfarmersmarket",
  "discovered_url": "https://www.facebook.com/apexfarmersmarket",
  "discovered_domain": "facebook.com",
  "link_text": "Facebook",
  "is_internal": false,
  "follow_allowed": false,
  "depth": 1,
  "discovery_method": "html_anchor",
  "discovered_at": "2026-05-16T11:45:00Z"
}
```

---

## Error Artifact Contract

`02_discovered_links_errors.jsonl` is for unexpected processing failures.

Each error record must include:

```text
run_id
stage_name
source_lead_id
source_url
error_type
message
retryable
created_at
```

Example:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "stage_name": "discover_links",
  "source_lead_id": "lead_000017",
  "source_url": "https://examplemarket.org/",
  "error_type": "html_parse_error",
  "message": "HTML parser failed unexpectedly",
  "retryable": false,
  "created_at": "2026-05-16T11:47:00Z"
}
```

Network failures while fetching the source page should produce an error record.

Expected ignored hrefs such as `mailto:`, `tel:`, empty hrefs, and fragment-only links should usually be counted in the summary, not written as errors.

---

## Summary Artifact Contract

`02_discovered_links_summary.json` must contain one JSON object.

Required fields:

```text
stage_name
stage_number
input_records
processed_sources
skipped_sources
source_fetch_errors
output_records
unique_links
internal_links
external_links
ignored_empty_href_count
ignored_fragment_count
ignored_javascript_count
ignored_mailto_count
ignored_tel_count
malformed_href_count
error_records
cap_limited_sources
started_at
completed_at
```

Example:

```json
{
  "stage_name": "discover_links",
  "stage_number": "02",
  "input_records": 100,
  "processed_sources": 81,
  "skipped_sources": 19,
  "source_fetch_errors": 3,
  "output_records": 1440,
  "unique_links": 1440,
  "internal_links": 1120,
  "external_links": 320,
  "ignored_empty_href_count": 4,
  "ignored_fragment_count": 12,
  "ignored_javascript_count": 3,
  "ignored_mailto_count": 1,
  "ignored_tel_count": 1,
  "malformed_href_count": 2,
  "error_records": 3,
  "cap_limited_sources": 4,
  "started_at": "2026-05-16T11:40:00Z",
  "completed_at": "2026-05-16T11:47:00Z"
}
```

---

## StageResult Contract

The stage harness must return a serializable `StageResult`.

Required fields:

```text
stage_id
stage_number
stage_name
status
consumed_artifacts
produced_artifacts
summary_artifact
error_artifact
counts
started_at
completed_at
```

Example:

```json
{
  "stage_id": "02_discover_links",
  "stage_number": "02",
  "stage_name": "discover_links",
  "status": "completed",
  "consumed_artifacts": [
    "01_validated_sources.jsonl"
  ],
  "produced_artifacts": [
    "02_discovered_links.jsonl"
  ],
  "summary_artifact": "02_discovered_links_summary.json",
  "error_artifact": "02_discovered_links_errors.jsonl",
  "counts": {
    "input_records": 100,
    "processed_sources": 81,
    "skipped_sources": 19,
    "source_fetch_errors": 3,
    "output_records": 1440,
    "internal_links": 1120,
    "external_links": 320,
    "error_records": 3
  },
  "started_at": "2026-05-16T11:40:00Z",
  "completed_at": "2026-05-16T11:47:00Z"
}
```

---

## Suggested Python Components

### Focused function

```text
extract_links_from_html(html, base_url) -> list[ExtractedLink]
```

This function should:

- parse HTML
- find `<a href>` tags
- extract `raw_href`
- extract `link_text`
- ignore obvious non-web hrefs
- resolve relative URLs to absolute URLs

It should not know about:

- JSONL
- manifest
- run folders
- stage paths
- source lead IDs

---

### Focused function

```text
is_internal_link(source_url, discovered_url) -> bool
```

This function should compare registered domains and treat `www` as equivalent.

---

### Stage harness

```text
run_discover_links(input_path, stage_paths, run_id, config) -> StageResult
```

The harness should:

1. Read `01_validated_sources.jsonl`.
2. Skip non-processable source records.
3. Fetch each valid source URL.
4. Call `extract_links_from_html()`.
5. Determine internal/external status.
6. Deduplicate discovered links per source.
7. Apply configured caps.
8. Write `02_discovered_links.jsonl`.
9. Write `02_discovered_links_errors.jsonl`.
10. Write `02_discovered_links_summary.json`.
11. Return `StageResult`.

---

## Configuration

Recommended config values:

```json
{
  "timeout_seconds": 15,
  "user_agent": "FarmlessBot/0.1",
  "max_links_per_source_page": 500,
  "max_internal_links_per_source": 200,
  "max_external_links_per_source": 100,
  "record_external_links": true,
  "follow_external_links": false
}
```

---

## Implementation Rules

1. Preserve `source_lead_id` from the input record.
2. Preserve the source page as `source_url`.
3. Fetch only the source page represented by `final_url`.
4. Do not fetch discovered links in this stage.
5. Do not score links in this stage.
6. Do not extract facts in this stage.
7. Do not convert HTML to markdown in this stage.
8. Do not follow external links.
9. Record external links if `record_external_links = true`.
10. Set `follow_allowed = true` only for internal links.
11. Ignore empty, fragment-only, JavaScript, mailto, and tel links.
12. Deduplicate links per source page.
13. Apply configured caps.
14. All timestamps must be ISO-8601 strings.
15. All output files must be valid JSON or JSONL.
16. The stage must not update `manifest.json` directly.

---

# Passing Criteria for Tester Agent

## Unit Tests for `extract_links_from_html()`

### Test 1: extracts simple absolute link

Given HTML:

```html
<a href="https://example.org/vendors">Vendors</a>
```

Expected:

```text
one link extracted
raw_href = https://example.org/vendors
discovered_url = https://example.org/vendors
link_text = Vendors
```

---

### Test 2: resolves relative link

Given:

```text
base_url = https://example.org/
```

And HTML:

```html
<a href="/vendors">Vendors</a>
```

Expected:

```text
discovered_url = https://example.org/vendors
```

---

### Test 3: extracts link text

Given HTML:

```html
<a href="/visit">Visit Us</a>
```

Expected:

```text
link_text = Visit Us
```

---

### Test 4: ignores empty href

Given HTML:

```html
<a href="">Empty</a>
```

Expected:

```text
zero links extracted
```

---

### Test 5: ignores fragment-only href

Given HTML:

```html
<a href="#top">Back to top</a>
```

Expected:

```text
zero links extracted
```

---

### Test 6: ignores javascript href

Given HTML:

```html
<a href="javascript:void(0)">Menu</a>
```

Expected:

```text
zero links extracted
```

---

### Test 7: ignores mailto and tel links

Given HTML:

```html
<a href="mailto:info@example.org">Email</a>
<a href="tel:5551234567">Call</a>
```

Expected:

```text
zero links extracted
```

---

### Test 8: handles nested text inside anchor

Given HTML:

```html
<a href="/vendors"><span>Our</span> Vendors</a>
```

Expected:

```text
link_text contains "Our Vendors"
```

---

## Unit Tests for `is_internal_link()`

### Test 9: same domain is internal

Given:

```text
source_url = https://example.org/
discovered_url = https://example.org/vendors
```

Expected:

```text
is_internal = true
```

---

### Test 10: www is treated as same domain

Given:

```text
source_url = https://www.example.org/
discovered_url = https://example.org/vendors
```

Expected:

```text
is_internal = true
```

---

### Test 11: different domain is external

Given:

```text
source_url = https://example.org/
discovered_url = https://facebook.com/example
```

Expected:

```text
is_internal = false
```

---

## Stage Harness Tests

### Test 12: reads validated sources and writes discovered links

Given one valid HTML source record and mocked HTML with two links.

Expected:

```text
02_discovered_links.jsonl exists
file contains two JSONL records
each record contains source_lead_id
each record contains source_url
each record contains discovered_url
```

---

### Test 13: skips non-HTML sources

Given an input record with:

```text
validation_status = non_html
```

Expected:

```text
source is skipped
processed_sources count does not include it
skipped_sources count includes it
no discovered links are written for it
```

---

### Test 14: skips broken sources

Given an input record with:

```text
validation_status = broken
```

Expected:

```text
source is skipped
no fetch attempted
skipped_sources increments
```

---

### Test 15: preserves source identity

Given input:

```json
{
  "source_lead_id": "lead_000001",
  "final_url": "https://example.org/",
  "validation_status": "valid",
  "content_type": "text/html"
}
```

Expected every output link from that page includes:

```text
source_lead_id = lead_000001
source_url = https://example.org/
```

---

### Test 16: records internal and external links

Given mocked HTML:

```html
<a href="/vendors">Vendors</a>
<a href="https://facebook.com/examplemarket">Facebook</a>
```

Expected output contains:

```text
/vendors record has is_internal = true and follow_allowed = true
facebook record has is_internal = false and follow_allowed = false
```

---

### Test 17: deduplicates links per source

Given mocked HTML:

```html
<a href="/vendors">Vendors</a>
<a href="/vendors">Our Vendors</a>
```

Expected:

```text
only one output record for https://example.org/vendors
```

---

### Test 18: writes summary JSON

After running the stage:

```text
02_discovered_links_summary.json exists
```

Expected fields:

```text
stage_name = discover_links
stage_number = 02
input_records
processed_sources
skipped_sources
output_records
internal_links
external_links
started_at
completed_at
```

---

### Test 19: handles source fetch error

Given a valid source whose fetch raises an exception.

Expected:

```text
02_discovered_links_errors.jsonl exists
error record includes source_lead_id
error record includes source_url
error record includes error_type
summary source_fetch_errors increments
```

---

### Test 20: applies max link cap

Given mocked HTML with more links than `max_links_per_source_page`.

Expected:

```text
output records do not exceed configured cap
summary cap_limited_sources increments
```

---

### Test 21: returns serializable StageResult

Expected:

```text
StageResult can be converted to dict
StageResult can be serialized to JSON
StageResult includes consumed_artifacts
StageResult includes produced_artifacts
StageResult includes counts
```

---

### Test 22: manifest is not updated by the stage

Expected:

```text
run_discover_links returns StageResult
stage itself does not directly modify manifest.json
```

The orchestrator owns manifest updates.

---

### Test 23: does not fetch discovered links

Given mocked HTML with:

```html
<a href="/vendors">Vendors</a>
```

Expected:

```text
stage fetches only source final_url
stage does not fetch https://example.org/vendors
```

---

## Definition of Done

This stage is complete when:

1. The stage reads `01_validated_sources.jsonl`.
2. The stage processes only valid HTML source records.
3. The stage fetches each processable source URL.
4. The stage extracts `<a href>` links.
5. The stage resolves relative links into absolute links.
6. The stage filters obvious non-web hrefs.
7. The stage marks links as internal or external.
8. The stage records external links but does not follow them.
9. The stage writes `02_discovered_links.jsonl`.
10. The stage writes `02_discovered_links_summary.json`.
11. The stage writes `02_discovered_links_errors.jsonl`.
12. The stage returns a JSON-serializable `StageResult`.
13. Unit tests cover extraction, relative URL resolution, internal/external detection, skip behavior, deduplication, caps, non-web href filtering, and error handling.
14. The stage does not score links, fetch discovered links, extract facts, convert markdown, follow external links, or update the manifest directly.

## Implementation

**Entry function:** `run_discover_links(input_path, stage_paths, run_id, config, fetcher, registry)`
[`stages/discover_links.py`](../../farmles_harvester/stages/discover_links.py)

Call sequence:
1. `stream_jsonl()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — streams validated source records
2. `fetcher.fetch(final_url)` — [`web/fetcher.py`](../../farmles_harvester/web/fetcher.py) — fetches the source page
3. `extract_links_from_html()` — [`web/html_utils.py`](../../farmles_harvester/web/html_utils.py) — extracts `<a href>` links
4. `normalize_url()` / `is_internal_link()` — [`web/url_utils.py`](../../farmles_harvester/web/url_utils.py) — normalizes and classifies each link
5. `score_discovered_link()` — [`stages/score_candidate_urls.py`](../../farmles_harvester/stages/score_candidate_urls.py) — pre-scores links during discovery (fast mode)
6. `evaluate_url_strength()` — [`registry/evaluation.py`](../../farmles_harvester/registry/evaluation.py) — registry-based skip decision
7. `JsonlWriter` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — writes output artifact

Input field contract: `VALIDATED_SOURCE_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)
