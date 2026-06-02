# Validate URL Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

The `validate_urls` stage takes normalized source lead records and checks whether each normalized URL is reachable, what it resolves to, and whether it is usable for later crawling.

This stage does **not** extract farmers market data.  
This stage does **not** discover internal links.  
This stage only validates source leads as web sources.

---

## Stage Name

```text
validate_urls
```

## Stage Number

```text
01
```

## Consumed Artifact

```text
00_normalized_source_leads.jsonl
```

Each input record represents one normalized source lead.

Example input record:

```json
{
  "source_lead_id": "lead_000001",
  "input_url": "apexfarmersmarket.com",
  "normalized_url": "https://apexfarmersmarket.com/",
  "status": "normalized",
  "input_line": 3
}
```

---

## Produced Artifacts

```text
01_validated_sources.jsonl
01_validated_sources_summary.json
01_validated_sources_errors.jsonl
```

---

## Core Responsibility

For each normalized source lead:

1. Read `normalized_url`.
2. Attempt to fetch the URL.
3. Follow redirects.
4. Record the final resolved URL.
5. Record HTTP status.
6. Record content type.
7. Determine a validation status.
8. Write one validated source record per input record.
9. Write processing failures to the errors artifact.
10. Write a summary artifact.

---

## Non-Responsibilities

This stage must not:

- extract market hours
- extract vendors
- extract locations
- discover internal links
- convert HTML to markdown
- call an LLM
- classify candidate pages
- decide final canonical market identity

---

## Validation Status Values

Allowed `validation_status` values:

```text
valid
redirected
broken
blocked
non_html
timeout
invalid_url
fetch_error
```

### Meaning

```text
valid
```

The URL returned a successful HTML response without redirect.

```text
redirected
```

The URL successfully resolved after one or more redirects.

```text
broken
```

The URL resolved but returned an error-like HTTP status such as 404 or 410.

```text
blocked
```

The site refused access, commonly 401, 403, or bot-blocking behavior.

```text
non_html
```

The URL resolved successfully but content type is not HTML, such as PDF, image, or plain file.

```text
timeout
```

The request exceeded the configured timeout.

```text
invalid_url
```

The normalized URL is malformed or cannot be parsed as a URL.

```text
fetch_error
```

Network or request failure not covered above.

---

## Output Record Contract

Each line in `01_validated_sources.jsonl` must be one JSON object.

Required fields:

```text
run_id
source_lead_id
input_url
normalized_url
final_url
domain
validation_status
http_status
content_type
redirected
redirect_chain
validated_at
```

Optional fields:

```text
failure_reason
title
```

Example successful record:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000001",
  "input_url": "apexfarmersmarket.com",
  "normalized_url": "https://apexfarmersmarket.com/",
  "final_url": "https://www.apexfarmersmarket.com/",
  "domain": "apexfarmersmarket.com",
  "validation_status": "redirected",
  "http_status": 200,
  "content_type": "text/html",
  "redirected": true,
  "redirect_chain": [
    "https://apexfarmersmarket.com/",
    "https://www.apexfarmersmarket.com/"
  ],
  "title": "Apex Farmers Market",
  "validated_at": "2026-05-16T11:35:00Z"
}
```

Example broken record:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000002",
  "input_url": "badsite.example",
  "normalized_url": "https://badsite.example/",
  "final_url": null,
  "domain": "badsite.example",
  "validation_status": "fetch_error",
  "http_status": null,
  "content_type": null,
  "redirected": false,
  "redirect_chain": [],
  "failure_reason": "dns_failed",
  "validated_at": "2026-05-16T11:35:05Z"
}
```

---

## Error Artifact Contract

`01_validated_sources_errors.jsonl` is for processing errors that prevent normal validation handling.

Each error record must include:

```text
run_id
stage_name
source_lead_id
normalized_url
error_type
message
retryable
created_at
```

Example:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "stage_name": "validate_urls",
  "source_lead_id": "lead_000017",
  "normalized_url": "https://example.com/",
  "error_type": "unexpected_exception",
  "message": "Unexpected parser failure",
  "retryable": false,
  "created_at": "2026-05-16T11:36:00Z"
}
```

Important distinction:

A 404, timeout, or DNS failure should usually still produce a normal validated source record with an appropriate `validation_status`.

The errors artifact is for unexpected stage-level failures.

---

## Summary Artifact Contract

`01_validated_sources_summary.json` must contain one JSON object.

Required fields:

```text
stage_name
stage_number
input_records
output_records
error_records
valid_count
redirected_count
broken_count
blocked_count
non_html_count
timeout_count
invalid_url_count
fetch_error_count
started_at
completed_at
```

Example:

```json
{
  "stage_name": "validate_urls",
  "stage_number": "01",
  "input_records": 100,
  "output_records": 100,
  "error_records": 0,
  "valid_count": 61,
  "redirected_count": 21,
  "broken_count": 7,
  "blocked_count": 3,
  "non_html_count": 2,
  "timeout_count": 4,
  "invalid_url_count": 1,
  "fetch_error_count": 1,
  "started_at": "2026-05-16T11:30:00Z",
  "completed_at": "2026-05-16T11:35:00Z"
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
  "stage_id": "01_validate_urls",
  "stage_number": "01",
  "stage_name": "validate_urls",
  "status": "completed",
  "consumed_artifacts": [
    "00_normalized_source_leads.jsonl"
  ],
  "produced_artifacts": [
    "01_validated_sources.jsonl"
  ],
  "summary_artifact": "01_validated_sources_summary.json",
  "error_artifact": "01_validated_sources_errors.jsonl",
  "counts": {
    "input_records": 100,
    "output_records": 100,
    "error_records": 0,
    "valid_count": 61,
    "redirected_count": 21,
    "broken_count": 7,
    "blocked_count": 3,
    "non_html_count": 2,
    "timeout_count": 4,
    "invalid_url_count": 1,
    "fetch_error_count": 1
  },
  "started_at": "2026-05-16T11:30:00Z",
  "completed_at": "2026-05-16T11:35:00Z"
}
```

---

## Suggested Python Components

### Pure / focused function

```text
validate_url(normalized_url, timeout_seconds) -> ValidatedUrlResult
```

This function should handle one URL.

It should not know about:

- JSONL
- manifest
- stage paths
- run folders
- source lead IDs

### Stage harness

```text
run_validate_urls(input_path, stage_paths, run_id, config) -> StageResult
```

The harness should:

1. Read input JSONL.
2. Call `validate_url()` per record.
3. Write `01_validated_sources.jsonl`.
4. Write `01_validated_sources_errors.jsonl`.
5. Write `01_validated_sources_summary.json`.
6. Return `StageResult`.

---

## Implementation

**Entry function:** `run_validate_urls(input_path, stage_paths, run_id, config, fetcher)`
[`stages/validate_urls.py`](../../farmles_harvester/stages/validate_urls.py)

Call sequence:
1. `read_jsonl()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — reads normalized source leads
2. `fetcher.fetch(normalized_url)` — [`web/fetcher.py`](../../farmles_harvester/web/fetcher.py) — performs HTTP fetch, follows redirects
3. `_classify_response()` — local helper — maps HTTP response to `validation_status`
4. `write_jsonl()` / `write_json()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — writes output and summary artifacts

Input field contract: `NORMALIZED_SOURCE_LEAD_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)
Output field contract: `VALIDATED_SOURCE_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)

---

## Configuration

Recommended config values:

```json
{
  "timeout_seconds": 15,
  "max_redirects": 10,
  "user_agent": "FarmlessBot/0.1",
  "html_content_types": [
    "text/html",
    "application/xhtml+xml"
  ]
}
```

---

## Implementation Rules

1. Preserve `source_lead_id`, `input_url`, and `normalized_url` from input.
2. Write exactly one output record per input record whenever possible.
3. Do not drop failed URLs silently.
4. Do not treat redirects as errors.
5. Do not classify farmers market relevance in this stage.
6. Do not extract links in this stage.
7. Do not write large HTML content in this stage.
8. All timestamps must be ISO-8601 strings.
9. All output files must be valid JSON or JSONL.
10. The stage must be deterministic except for network-dependent results.

---

# Passing Criteria for Tester Agent

## Unit Tests for `validate_url()`

### Test 1: valid HTML URL

Given a URL that returns:

```text
HTTP 200
Content-Type: text/html
No redirects
```

Expected:

```text
validation_status = valid
http_status = 200
content_type contains text/html
redirected = false
final_url = original URL
```

---

### Test 2: redirected HTML URL

Given a URL that redirects to another URL and ends with:

```text
HTTP 200
Content-Type: text/html
```

Expected:

```text
validation_status = redirected
redirected = true
redirect_chain has at least 2 URLs
final_url = last URL in redirect chain
```

---

### Test 3: broken URL HTTP status

Given a URL that returns:

```text
HTTP 404
```

Expected:

```text
validation_status = broken
http_status = 404
final_url is not null if response was received
```

---

### Test 4: blocked URL

Given a URL that returns:

```text
HTTP 403
```

Expected:

```text
validation_status = blocked
http_status = 403
```

---

### Test 5: non-HTML URL

Given a URL that returns:

```text
HTTP 200
Content-Type: application/pdf
```

Expected:

```text
validation_status = non_html
http_status = 200
content_type = application/pdf
```

---

### Test 6: timeout

Given a request that times out.

Expected:

```text
validation_status = timeout
http_status = null
failure_reason contains timeout
```

---

### Test 7: invalid URL

Given a malformed URL.

Expected:

```text
validation_status = invalid_url
http_status = null
final_url = null
```

---

## Stage Harness Tests

### Test 8: reads input JSONL and writes output JSONL

Given an input file with 3 normalized source lead records.

Expected:

```text
01_validated_sources.jsonl exists
it contains 3 JSONL lines
each line contains source_lead_id
each line contains normalized_url
each line contains validation_status
```

---

### Test 9: preserves source lead identity

Given:

```json
{
  "source_lead_id": "lead_000001",
  "input_url": "example.com",
  "normalized_url": "https://example.com/"
}
```

Expected output record includes the same:

```text
source_lead_id
input_url
normalized_url
```

---

### Test 10: writes summary JSON

After running the stage:

```text
01_validated_sources_summary.json exists
```

Expected fields:

```text
stage_name = validate_urls
stage_number = 01
input_records
output_records
error_records
started_at
completed_at
```

---

### Test 11: output count matches input count

Given 5 input records with normal expected failures such as 404 or timeout.

Expected:

```text
input_records = 5
output_records = 5
```

Reason:

404 and timeout are validation outcomes, not dropped records.

---

### Test 12: unexpected exception goes to error artifact

Given one record causes an unexpected exception inside the stage harness.

Expected:

```text
01_validated_sources_errors.jsonl exists
error record includes source_lead_id
error record includes error_type
error record includes retryable
```

---

### Test 13: returns serializable StageResult

Expected:

```text
StageResult can be converted to dict
StageResult can be serialized to JSON
StageResult includes consumed_artifacts
StageResult includes produced_artifacts
StageResult includes counts
```

---

### Test 14: no HTML body stored in output records

Expected:

```text
01_validated_sources.jsonl records do not contain full HTML body
```

This stage may record page title, but not raw content.

---

### Test 15: manifest is not updated by the stage

Expected:

```text
run_validate_urls returns StageResult
stage itself does not directly modify manifest.json
```

The orchestrator owns manifest updates.

---

## Definition of Done

This stage is complete when:

1. The stage can read `00_normalized_source_leads.jsonl`.
2. The stage writes `01_validated_sources.jsonl`.
3. The stage writes `01_validated_sources_summary.json`.
4. The stage writes `01_validated_sources_errors.jsonl`.
5. The stage returns a JSON-serializable `StageResult`.
6. Unit tests cover valid, redirected, broken, blocked, non-HTML, timeout, and invalid URL cases.
7. Harness tests confirm artifact creation and record counts.
8. The stage does not discover links, extract facts, convert markdown, or modify the manifest directly.
