# Sprint 5 Prompt: Stage 01 Harness for `validate_urls`

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 5 only**.

Sprint 0 verified tooling.  
Sprint 1 implemented pure logic functions and unit tests.  
Sprint 2 implemented the Stage 00 harness for `normalize_source_leads`.  
Sprint 3 added lightweight record contracts.  
Sprint 4 formalized pipeline primitives: `StagePaths`, `StageResult`, and JSONL helpers.

Sprint 5 should now implement the Stage 01 harness:

```text
01_validate_urls
```

Do not implement Stage 02 yet.  
Do not implement the full orchestrator yet.  
Do not use real internet in tests.  
Do not add GitHub or SQL functionality.

---

# Goal

Implement a pipeline stage harness that reads normalized source lead records and validates each URL using an injectable fetcher.

The stage should produce:

```text
01_validated_sources.jsonl
01_validated_sources_summary.json
01_validated_sources_errors.jsonl
```

and return a JSON-serializable `StageResult`.

Pipeline flow for this sprint:

```text
00_normalized_source_leads.jsonl
   ↓
run_validate_urls()
   ↓
01_validated_sources.jsonl
01_validated_sources_summary.json
01_validated_sources_errors.jsonl
StageResult
```

---

# Stage Purpose

`validate_urls` checks whether each normalized URL is reachable and records the result.

It answers:

```text
Does this normalized URL resolve to a usable web source?
```

It does **not** discover links.  
It does **not** extract market facts.  
It does **not** convert HTML to markdown.

---

# Required Files / Modules

Implement or update:

```text
farmles_harvester/
  stages/
    validate_urls.py

  web/
    fetcher.py

tests/
  harness/
    test_validate_urls_stage.py
```

Use existing shared infrastructure:

```text
farmles_harvester/pipeline/stage_paths.py
farmles_harvester/pipeline/stage_result.py
farmles_harvester/pipeline/jsonl.py
farmles_harvester/models/record_contracts.py
tests/helpers/fake_fetcher.py
```

If the fake fetcher from Sprint 0 needs extension to support redirects, timeouts, or exceptions, update it carefully and keep existing tests passing.

---

# Required Harness Function

Implement:

```python
run_validate_urls(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
    fetcher=None,
) -> StageResult
```

## Responsibilities

The harness must:

1. Read `00_normalized_source_leads.jsonl`.
2. Validate that input records contain required fields from `NORMALIZED_SOURCE_LEAD_REQUIRED`.
3. For each input record, read `normalized_url`.
4. Fetch the URL using the injected `fetcher`.
5. Classify the result into a validation status.
6. Write one output record per input record whenever possible.
7. Write summary JSON.
8. Write errors JSONL for malformed input records or unexpected stage errors.
9. Return a JSON-serializable `StageResult`.

---

# Input Artifact

```text
00_normalized_source_leads.jsonl
```

Each input record should satisfy:

```python
NORMALIZED_SOURCE_LEAD_REQUIRED
```

Expected required fields:

```text
run_id
source_lead_id
input_url
normalized_url
input_line
normalized_at
```

Example input record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "input_url": "apexfarmersmarket.com",
  "normalized_url": "https://apexfarmersmarket.com/",
  "input_line": 3,
  "normalization_notes": ["added_https_scheme"],
  "normalized_at": "2026-05-17T13:24:00Z"
}
```

---

# Output Artifacts

The stage must write:

```text
01_validated_sources.jsonl
01_validated_sources_summary.json
01_validated_sources_errors.jsonl
```

Use `StagePaths` to get the paths. Do not hardcode filenames in the harness.

---

# Validation Status Values

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

## Meaning

### `valid`

The URL returned a successful HTML response with no redirect.

Expected:

```text
HTTP 200
Content-Type contains text/html or application/xhtml+xml
redirected = false
```

### `redirected`

The URL redirected and eventually returned a successful HTML response.

Expected:

```text
HTTP 200
Content-Type contains text/html or application/xhtml+xml
redirected = true
redirect_chain has at least 2 URLs
```

### `broken`

The server responded with an error status such as:

```text
404
410
```

### `blocked`

The server refused access, commonly:

```text
401
403
```

### `non_html`

The URL resolved successfully but the response content type is not HTML.

Example:

```text
application/pdf
image/png
text/plain
```

### `timeout`

The fetcher raised a timeout-specific exception or returned a timeout result.

### `invalid_url`

The input record has a missing or malformed `normalized_url`.

### `fetch_error`

A network or fetcher failure not covered by the statuses above.

---

# Fetcher Contract

The stage must use an injectable fetcher.

Do not hardcode real network calls inside the harness.

Expected usage:

```python
response = fetcher.fetch(normalized_url)
```

The fake or real response should expose at least:

```text
url
status_code
content_type
text
```

Recommended optional fields:

```text
final_url
redirect_chain
```

If `final_url` is unavailable, use `response.url`.

If `redirect_chain` is unavailable, use an empty list unless redirected behavior is explicitly represented.

Automated tests must use fake fetchers. No real network.

---

# Output Record Contract

Write:

```text
01_validated_sources.jsonl
```

Each line must be one JSON object.

Each output record must satisfy:

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

Recommended additional fields:

```text
input_url
domain
http_status
content_type
redirected
redirect_chain
failure_reason
```

Example valid record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "input_url": "apexfarmersmarket.com",
  "normalized_url": "https://apexfarmersmarket.com/",
  "final_url": "https://apexfarmersmarket.com/",
  "domain": "apexfarmersmarket.com",
  "validation_status": "valid",
  "http_status": 200,
  "content_type": "text/html",
  "redirected": false,
  "redirect_chain": [],
  "validated_at": "2026-05-17T13:25:00Z"
}
```

Example redirected record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
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
  "validated_at": "2026-05-17T13:25:00Z"
}
```

Example broken record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_2",
  "input_url": "missing.example",
  "normalized_url": "https://missing.example/",
  "final_url": "https://missing.example/",
  "domain": "missing.example",
  "validation_status": "broken",
  "http_status": 404,
  "content_type": "text/html",
  "redirected": false,
  "redirect_chain": [],
  "failure_reason": "http_404",
  "validated_at": "2026-05-17T13:25:00Z"
}
```

---

# Error Artifact Contract

Write:

```text
01_validated_sources_errors.jsonl
```

Use this for malformed input records or unexpected processing failures.

Required fields:

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

Example malformed input error:

```json
{
  "run_id": "test-run",
  "stage_name": "validate_urls",
  "source_lead_id": "lead_3",
  "normalized_url": null,
  "error_type": "invalid_input_record",
  "message": "Missing required field: normalized_url",
  "retryable": false,
  "created_at": "2026-05-17T13:25:00Z"
}
```

Important distinction:

A 404, 403, timeout, or generic fetch failure should usually still produce an output record with an appropriate `validation_status`.

The errors artifact is for malformed input records or unexpected stage-level failures.

---

# Summary Artifact Contract

Write:

```text
01_validated_sources_summary.json
```

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
  "input_records": 7,
  "output_records": 7,
  "error_records": 0,
  "valid_count": 1,
  "redirected_count": 1,
  "broken_count": 1,
  "blocked_count": 1,
  "non_html_count": 1,
  "timeout_count": 1,
  "invalid_url_count": 0,
  "fetch_error_count": 1,
  "started_at": "2026-05-17T13:25:00Z",
  "completed_at": "2026-05-17T13:25:02Z"
}
```

---

# StageResult Contract

The harness must return a JSON-serializable `StageResult`.

Example:

```json
{
  "stage_id": "01_validate_urls",
  "stage_number": "01",
  "stage_name": "validate_urls",
  "status": "completed",
  "consumed_artifacts": ["00_normalized_source_leads.jsonl"],
  "produced_artifacts": ["01_validated_sources.jsonl"],
  "summary_artifact": "01_validated_sources_summary.json",
  "error_artifact": "01_validated_sources_errors.jsonl",
  "counts": {
    "input_records": 7,
    "output_records": 7,
    "error_records": 0,
    "valid_count": 1,
    "redirected_count": 1,
    "broken_count": 1,
    "blocked_count": 1,
    "non_html_count": 1,
    "timeout_count": 1,
    "invalid_url_count": 0,
    "fetch_error_count": 1
  },
  "started_at": "2026-05-17T13:25:00Z",
  "completed_at": "2026-05-17T13:25:02Z"
}
```

Artifact names should be relative filenames, not absolute paths.

---

# Classification Rules

Implement a focused helper if useful:

```python
classify_validation_response(response) -> dict
```

or keep classification inside the stage if small.

Expected classification:

## 200 HTML, no redirect

```text
validation_status = valid
```

## 200 HTML, redirect chain length > 1 or final_url differs from normalized_url

```text
validation_status = redirected
```

## 404 or 410

```text
validation_status = broken
```

## 401 or 403

```text
validation_status = blocked
```

## 200 but content type is not HTML

```text
validation_status = non_html
```

## timeout exception

```text
validation_status = timeout
```

## malformed or missing normalized_url

```text
validation_status = invalid_url
```

## other fetch exception

```text
validation_status = fetch_error
```

---

# Required Tests

Create or update:

```text
tests/harness/test_validate_urls_stage.py
```

Use fake fetchers. Do not use real network.

## Test 1: writes standard artifacts

Given a valid `00_normalized_source_leads.jsonl`, running `run_validate_urls()` should create:

```text
01_validated_sources.jsonl
01_validated_sources_summary.json
01_validated_sources_errors.jsonl
```

## Test 2: 200 HTML becomes valid

Fake response:

```text
status_code = 200
content_type = text/html
url = normalized_url
```

Expected:

```text
validation_status = valid
http_status = 200
redirected = false
```

## Test 3: redirect becomes redirected

Fake response:

```text
status_code = 200
content_type = text/html
final_url differs from normalized_url
redirect_chain contains original and final URL
```

Expected:

```text
validation_status = redirected
redirected = true
redirect_chain has at least 2 URLs
```

## Test 4: 404 becomes broken

Fake response:

```text
status_code = 404
```

Expected:

```text
validation_status = broken
http_status = 404
```

## Test 5: 403 becomes blocked

Fake response:

```text
status_code = 403
```

Expected:

```text
validation_status = blocked
http_status = 403
```

## Test 6: PDF/content-type non-html becomes non_html

Fake response:

```text
status_code = 200
content_type = application/pdf
```

Expected:

```text
validation_status = non_html
content_type = application/pdf
```

## Test 7: timeout becomes timeout

Fake fetcher raises a timeout-specific exception.

Expected:

```text
validation_status = timeout
failure_reason contains timeout
```

## Test 8: generic fetch exception becomes fetch_error

Fake fetcher raises a generic exception.

Expected:

```text
validation_status = fetch_error
failure_reason is present
```

## Test 9: missing normalized_url writes error or invalid output

Given an input record missing `normalized_url`.

Expected:

```text
error record is written
summary error_records increments
stage does not crash
```

If you also emit an output record with `validation_status = invalid_url`, that is acceptable as long as the behavior is consistent and tested.

## Test 10: output records satisfy `VALIDATED_SOURCE_REQUIRED`

For every output record:

```python
require_fields(record, VALIDATED_SOURCE_REQUIRED)
```

## Test 11: StageResult is JSON-serializable

After running the stage:

```python
json.dumps(result.to_dict())
```

should not raise.

## Test 12: writes only to provided StagePaths

Use `StagePaths.for_stage()` in the test and assert the stage writes to:

```text
paths.output_path
paths.summary_path
paths.errors_path
```

Do not duplicate filename derivation logic in the test.

---

# Boundaries

Do not implement:

- Stage 02 discover_links harness
- Stage 03 score_candidate_urls harness
- Stage 04 generate_markdown_pages harness
- full orchestrator
- manifest updates
- real internet smoke test
- Git/GitHub
- farmles_wiki import
- SQL export
- LLM extraction

This sprint is only:

```text
Stage 01 validate_urls harness + fake-fetcher tests
```

---

# Acceptance Criteria

Sprint 5 is complete when:

1. `run_validate_urls()` is implemented.
2. It reads `00_normalized_source_leads.jsonl`.
3. It uses an injected fetcher.
4. It writes `01_validated_sources.jsonl`.
5. It writes `01_validated_sources_summary.json`.
6. It writes `01_validated_sources_errors.jsonl`.
7. It returns a JSON-serializable `StageResult`.
8. Harness tests cover valid, redirected, broken, blocked, non_html, timeout, fetch_error, and malformed input cases.
9. Output records satisfy `VALIDATED_SOURCE_REQUIRED`.
10. Existing Stage 00 tests still pass.
11. No real network calls are used in tests.
12. No later pipeline stage is implemented.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Harness implemented.
3. Fake fetcher changes, if any.
4. Tests added.
5. Test command used.
6. Test result.
7. Any assumptions or deferred work.
