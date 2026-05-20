# Sprint 6 Prompt: Stage 02 + Stage 03 Harnesses

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 6 only**.

Sprint 0 verified tooling.  
Sprint 1 implemented pure logic functions and unit tests.  
Sprint 2 implemented the Stage 00 harness.  
Sprint 3 added lightweight record contracts.  
Sprint 4 formalized pipeline primitives.  
Sprint 5 implemented the Stage 01 `validate_urls` harness.

Sprint 6 should implement the next two deterministic pipeline stage harnesses:

```text
02_discover_links
03_score_candidate_urls
```

Do not implement Stage 04 yet.  
Do not implement the full orchestrator yet.  
Do not use real internet in tests.  
Do not add GitHub or SQL functionality.

---

# Goal

Implement the harnesses for Stage 02 and Stage 03 using the established pipeline pattern.

The flow for this sprint is:

```text
01_validated_sources.jsonl
   ↓
02_discover_links
   ↓
02_discovered_links.jsonl
   ↓
03_score_candidate_urls
   ↓
03_candidate_urls.jsonl
```

Each stage must write:

```text
{stage_number}_{artifact_name}.jsonl
{stage_number}_{artifact_name}_summary.json
{stage_number}_{artifact_name}_errors.jsonl
```

Each stage must return a JSON-serializable `StageResult`.

---

# Shared Rules for Both Stages

Both stage harnesses must:

1. Read their input JSONL artifact.
2. Validate required input fields using `record_contracts.py`.
3. Write output JSONL.
4. Write summary JSON.
5. Write errors JSONL.
6. Return a valid `StageResult`.
7. Use `StagePaths`.
8. Use JSONL helpers.
9. Keep stage responsibilities narrow.
10. Avoid real network calls in tests.

The test pattern should follow prior harness tests:

```text
input artifact
   ↓
run stage harness
   ↓
output artifact + summary + errors + StageResult
```

---

# Stage 02: `discover_links`

## Purpose

`discover_links` reads validated source records, fetches each valid HTML source page, extracts links from `<a href="...">` tags, and writes discovered link records.

It answers:

```text
What links are present on this validated source page?
```

It does **not** score links.  
It does **not** fetch discovered links.  
It does **not** convert pages to markdown.

---

## Input Artifact

```text
01_validated_sources.jsonl
```

Input records should satisfy:

```python
VALIDATED_SOURCE_REQUIRED
```

Minimum required fields:

```text
run_id
source_lead_id
normalized_url
final_url
validation_status
validated_at
```

Stage 02 should process only records where:

```text
validation_status in ["valid", "redirected"]
final_url is not null
content_type contains "text/html" or "application/xhtml+xml"
```

If `content_type` is `null` or absent, treat the record as non-HTML and skip it.

Skip broken, blocked, timeout, fetch_error, invalid_url, and non_html records.

Skipped records are not errors. Count them in summary.

---

## Required Harness Function

Implement in:

```text
farmles_harvester/stages/discover_links.py
```

Function:

```python
run_discover_links(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
    fetcher=None,
) -> StageResult
```

The harness must use an injectable fetcher.

The harness must fetch `final_url` from each input record, not `normalized_url`. `final_url` is the actual resolved URL after any redirects (set by Stage 01). Fetching `normalized_url` would re-follow the redirect unnecessarily and may return a different page.

Automated tests must use a fake fetcher. No real internet.

---

## Stage 02 Output Artifact

Write:

```text
02_discovered_links.jsonl
```

Each output record should satisfy:

```python
DISCOVERED_LINK_REQUIRED
```

Required fields:

```text
run_id
source_lead_id
source_url
discovered_url
link_text
is_internal
follow_allowed
```

Recommended additional fields:

```text
raw_href
source_domain
discovered_domain
depth
discovery_method
discovered_at
```

`depth` represents how many hops from the seed URL this link was discovered. In Sprint 6, the stage only crawls the source page directly, so all links discovered here are `depth = 1`. Future sprints may support deeper crawls where depth increments with each hop; writing this field now allows the schema to remain stable.

Example output record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "source_url": "https://apex.example/",
  "raw_href": "/vendors",
  "discovered_url": "https://apex.example/vendors",
  "link_text": "Vendors",
  "is_internal": true,
  "follow_allowed": true,
  "depth": 1,
  "discovery_method": "html_anchor",
  "discovered_at": "2026-05-17T13:30:00Z"
}
```

External links should be recorded, but not followed:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "source_url": "https://apex.example/",
  "raw_href": "https://facebook.com/apexmarket",
  "discovered_url": "https://facebook.com/apexmarket",
  "link_text": "Facebook",
  "is_internal": false,
  "follow_allowed": false,
  "depth": 1,
  "discovery_method": "html_anchor",
  "discovered_at": "2026-05-17T13:30:00Z"
}
```

---

## Stage 02 Summary Artifact

Write:

```text
02_discovered_links_summary.json
```

Required fields:

```text
stage_name
stage_number
input_records
processed_sources
skipped_sources
source_fetch_errors
output_records
internal_links
external_links
error_records
started_at
completed_at
```

Optional fields:

```text
ignored_empty_href_count
ignored_fragment_count
ignored_javascript_count
ignored_mailto_count
ignored_tel_count
```

---

## Stage 02 Errors Artifact

Write:

```text
02_discovered_links_errors.jsonl
```

Use this for unexpected processing failures or source fetch failures.

Required fields:

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

Expected ignored links such as `mailto:`, `tel:`, `javascript:`, blank hrefs, and fragment-only hrefs should usually be counted in summary, not written as errors.

---

## Stage 02 Tests

Create:

```text
tests/harness/test_discover_links_stage.py
```

Required tests:

1. Writes standard artifacts.
2. Processes only valid/redirected HTML source records.
3. Skips broken/non_html/timeout records and counts skipped records.
4. Uses fake fetcher to fetch only the source `final_url`.
5. Extracts internal links.
6. Extracts external links.
7. Marks internal links with `is_internal = true` and `follow_allowed = true`.
8. Marks external links with `is_internal = false` and `follow_allowed = false`.
9. Ignores mailto/tel/javascript/fragment-only links.
10. Does not fetch discovered links.
11. Output records satisfy `DISCOVERED_LINK_REQUIRED`.
12. StageResult is JSON-serializable.
13. Stage writes only to provided `StagePaths`.

---

# Stage 03: `score_candidate_urls`

## Purpose

`score_candidate_urls` reads discovered link records and scores them using deterministic rules.

It answers:

```text
Which discovered URLs look useful enough to become candidate URLs?
```

It does **not** fetch URLs.  
It does **not** read page content.  
It does **not** convert pages to markdown.  
It does **not** call an LLM.

---

## Input Artifact

```text
02_discovered_links.jsonl
```

Input records should satisfy:

```python
DISCOVERED_LINK_REQUIRED
```

Minimum required fields:

```text
run_id
source_lead_id
source_url
discovered_url
link_text
is_internal
follow_allowed
```

---

## Required Harness Function

Add to the existing file (do NOT overwrite Sprint 1 logic):

```text
farmles_harvester/stages/score_candidate_urls.py
```

`score_candidate_urls.py` already contains `score_discovered_link()`, `LinkRecord`, and `CandidateScore` from Sprint 1. Add `run_score_candidate_urls()` to that file. Do not remove or replace any existing functions.

Function to add:

```python
run_score_candidate_urls(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
) -> StageResult
```

This harness must call the existing Sprint 1 pure logic function:

```python
score_discovered_link(link_record, config=None)
```

---

## Stage 03 Output Artifact

Write:

```text
03_candidate_urls.jsonl
```

Each output record should satisfy:

```python
CANDIDATE_URL_REQUIRED
```

Required fields:

```text
run_id
source_lead_id
source_url
candidate_url
candidate_type
candidate_score
candidate_status
```

Recommended additional fields:

```text
link_text
candidate_strength
score_reasons
scored_at
```

Example selected record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "source_url": "https://apex.example/",
  "candidate_url": "https://apex.example/vendors",
  "link_text": "Vendors",
  "candidate_type": "vendor_page",
  "candidate_score": 80,
  "candidate_status": "selected",
  "candidate_strength": "strong",
  "score_reasons": [
    "url_contains_vendor",
    "link_text_contains_vendor",
    "internal_follow_allowed"
  ],
  "scored_at": "2026-05-17T13:31:00Z"
}
```

Example rejected record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "source_url": "https://apex.example/",
  "candidate_url": "https://apex.example/privacy-policy",
  "link_text": "Privacy Policy",
  "candidate_type": "low_value_page",
  "candidate_score": 0,
  "candidate_status": "rejected",
  "candidate_strength": "weak",
  "score_reasons": [
    "url_contains_low_value_path"
  ],
  "scored_at": "2026-05-17T13:31:00Z"
}
```

External links should generally become:

```text
candidate_status = external_reference
candidate_type = external_reference
```

---

## Stage 03 Summary Artifact

Write:

```text
03_candidate_urls_summary.json
```

Required fields:

```text
stage_name
stage_number
input_records
output_records
error_records
selected_count
rejected_count
external_reference_count
strong_candidate_count
medium_candidate_count
weak_candidate_count
started_at
completed_at
```

Optional fields:

```text
vendor_page_count
hours_location_page_count
calendar_events_page_count
about_contact_page_count
general_market_page_count
low_value_page_count
unknown_count
```

---

## Stage 03 Errors Artifact

Write:

```text
03_candidate_urls_errors.jsonl
```

Use this for malformed input records or unexpected scoring failures.

Required fields:

```text
run_id
stage_name
source_lead_id
discovered_url
error_type
message
retryable
created_at
```

---

## Stage 03 Tests

Create:

```text
tests/harness/test_score_candidate_urls_stage.py
```

Required tests:

1. Writes standard artifacts.
2. Reads `02_discovered_links.jsonl`.
3. Calls scoring logic for each valid discovered link record.
4. `/vendors` link becomes selected `vendor_page`.
5. `/visit` link becomes selected `hours_location_page`.
6. `/events` link becomes selected `calendar_events_page`.
7. `/privacy-policy` link becomes rejected `low_value_page`.
8. External link becomes `external_reference`.
9. Output records satisfy `CANDIDATE_URL_REQUIRED`.
10. Summary counts selected/rejected/external_reference records.
11. Malformed input record writes an error and does not crash the whole stage.
12. StageResult is JSON-serializable.
13. Stage writes only to provided `StagePaths`.
14. Stage does not fetch URLs.

---

# Combined Harness Test Optional

Optional but useful:

Create an integration-style harness test that runs Stage 02 and Stage 03 back-to-back using fake HTML.

Flow:

```text
01_validated_sources.jsonl
   ↓
run_discover_links()
   ↓
02_discovered_links.jsonl
   ↓
run_score_candidate_urls()
   ↓
03_candidate_urls.jsonl
```

Expected:

```text
/vendors is discovered and selected
/visit is discovered and selected
/privacy-policy is discovered and rejected
facebook link is discovered and marked external_reference
```

Do not use real network.

---

# Non-Responsibilities

Do not implement:

- Stage 04 generate_markdown_pages harness
- full orchestrator
- manifest updates
- real internet smoke test
- Git/GitHub
- farmles_wiki import
- SQL export
- LLM extraction

Sprint 6 is only:

```text
Stage 02 discover_links harness
Stage 03 score_candidate_urls harness
harness tests
optional combined harness test
```

---

# Acceptance Criteria

Sprint 6 is complete when:

1. `run_discover_links()` is implemented.
2. `run_discover_links()` writes output, summary, and error artifacts.
3. `run_discover_links()` returns a JSON-serializable `StageResult`.
4. Stage 02 output records satisfy `DISCOVERED_LINK_REQUIRED`.
5. `run_score_candidate_urls()` is implemented.
6. `run_score_candidate_urls()` writes output, summary, and error artifacts.
7. `run_score_candidate_urls()` returns a JSON-serializable `StageResult`.
8. Stage 03 output records satisfy `CANDIDATE_URL_REQUIRED`.
9. Harness tests exist for Stage 02.
10. Harness tests exist for Stage 03.
11. No real network calls are used in tests.
12. Existing Stage 00 and Stage 01 tests still pass.
13. No Stage 04 or orchestrator implementation is added.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Stage 02 harness implemented.
3. Stage 03 harness implemented.
4. Tests added.
5. Test command used.
6. Test result.
7. Any assumptions or deferred work.
