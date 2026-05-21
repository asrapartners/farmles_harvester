# Sprint 8 Prompt: Stage 04 Harness for `generate_markdown_pages`

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 8 only**.

Sprint 7 implemented and tested the pure HTML-to-Markdown converter logic:

```text
html_to_markdown()
normalize_markdown()
```

Sprint 8 should now wrap that logic in the Stage 04 pipeline harness:

```text
04_generate_markdown_pages
```

Do not implement the full orchestrator yet.  
Do not use real internet in tests.  
Do not add GitHub or SQL functionality.  
Do not implement `farmles_wiki` import logic.

---

# Goal

Implement the Stage 04 harness that reads selected candidate URLs, fetches their HTML with an injectable fetcher, converts the HTML to markdown, and writes lead-based generated wiki output.

Pipeline flow for this sprint:

```text
03_candidate_urls.jsonl
   ↓
run_generate_markdown_pages()
   ↓
04_markdown_pages.jsonl
04_markdown_pages_summary.json
04_markdown_pages_errors.jsonl
generated_wiki/
StageResult
```

---

# Stage Purpose

`generate_markdown_pages` turns selected candidate URLs into markdown files.

It answers:

```text
For each selected candidate URL, what markdown page should be generated for the source lead?
```

It does **not** decide final market identity.

It should write lead-based output:

```text
generated_wiki/{source_lead_id}/
```

It should not write final wiki market folders such as:

```text
markets/{market_slug}_{market_id}/
```

Market identity and importing into approved market folders belong to `farmles_wiki`.

---

# Required Files / Modules

Implement or update:

```text
farmles_harvester/
  stages/
    generate_markdown_pages.py

tests/
  harness/
    test_generate_markdown_pages_stage.py
```

Use existing shared infrastructure:

```text
farmles_harvester/pipeline/stage_paths.py
farmles_harvester/pipeline/stage_result.py
farmles_harvester/pipeline/jsonl.py
farmles_harvester/models/record_contracts.py
tests/helpers/fake_fetcher.py
```

Use existing Sprint 7 logic from `farmles_harvester/stages/generate_markdown_pages.py`:

```text
html_to_markdown()
normalize_markdown()
candidate_type_to_filename()
compute_content_hash()
```

Import `FetchTimeoutError` from `farmles_harvester.web.fetcher` to distinguish timeout from generic fetch errors (defined in Sprint 5).

---

# Required Harness Function

Implement:

```python
run_generate_markdown_pages(
    input_path: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
    fetcher=None,
) -> StageResult
```

## Responsibilities

The harness must:

1. Read `03_candidate_urls.jsonl`.
2. Validate input records using `CANDIDATE_URL_REQUIRED`.
3. Process only records where:

```text
candidate_status = selected
```

4. Skip rejected and external-reference records.
5. Fetch each selected `candidate_url` using the injected fetcher.
6. Convert HTML to markdown using `html_to_markdown()`.
7. Choose a markdown filename using `candidate_type_to_filename()`.
8. Avoid overwriting files when multiple URLs map to the same filename.
9. Write markdown files under:

```text
generated_wiki/{source_lead_id}/
```

10. Write `lead_metadata.json` once per source lead.
11. Write `04_markdown_pages.jsonl`.
12. Write `04_markdown_pages_summary.json`.
13. Write `04_markdown_pages_errors.jsonl`.
14. Return a JSON-serializable `StageResult`.

---

# Input Artifact

```text
03_candidate_urls.jsonl
```

Each input record should satisfy:

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

Example input record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "source_url": "https://apex.example/",
  "candidate_url": "https://apex.example/vendors",
  "candidate_type": "vendor_page",
  "candidate_score": 80,
  "candidate_status": "selected",
  "link_text": "Vendors",
  "candidate_strength": "strong",
  "score_reasons": [
    "url_contains_vendor",
    "link_text_contains_vendor"
  ],
  "scored_at": "2026-05-17T13:31:00Z"
}
```

Only selected records should be fetched and converted.

---

# Output Artifacts

The stage must write:

```text
04_markdown_pages.jsonl
04_markdown_pages_summary.json
04_markdown_pages_errors.jsonl
```

It must also write markdown files under:

```text
generated_wiki/
```

Example run output:

```text
runs/2026-05-17_132400_initial-import/
  04_markdown_pages.jsonl
  04_markdown_pages_summary.json
  04_markdown_pages_errors.jsonl

  generated_wiki/
    lead_1/
      lead_metadata.json
      vendors.md
      visit.md

    lead_2/
      lead_metadata.json
      index.md
```

---

# generated_wiki Folder Rule

Output must be grouped by source lead:

```text
generated_wiki/{source_lead_id}/
```

The harness derives `wiki_dir` from `stage_paths` — it is not a separate parameter:

```python
wiki_dir = stage_paths.output_path.parent / "generated_wiki"
```

All lead folders are written under `wiki_dir`. No extra parameter is needed.

Example:

```text
generated_wiki/lead_1/vendors.md
```

Do not write:

```text
generated_wiki/markets/apex-farmers-market_mkt-1/
```

Do not read or use `market_registry.jsonl`.

---

# Markdown Filename Rule

Use:

```python
candidate_type_to_filename(candidate_type)
```

Required mapping:

```text
general_market_page   → index.md
vendor_page           → vendors.md
hours_location_page   → visit.md
calendar_events_page  → events.md
about_contact_page    → about.md
unknown               → page.md
```

## Filename Collision Rule

If two selected records for the same `source_lead_id` map to the same filename, do not overwrite.

Example:

```text
vendors.md
vendors-2.md
vendors-3.md
```

This collision handling should be deterministic and tested.

---

# Markdown Content Rule

Use the Sprint 7 converter:

```python
html_to_markdown(html, source_url)
```

The markdown should:

- preserve factual text
- preserve headings
- preserve lists
- preserve link text
- apply light whitespace cleanup
- append source URL footer

Do not add YAML front matter.

Do not add `market_id`, `market_slug`, or `approved_for_extraction`.

---

# lead_metadata.json

Each source lead folder must contain:

```text
lead_metadata.json
```

Write it once per `source_lead_id`.

Minimum fields:

```text
source_lead_id
source_url
generated_at
```

Include these fields, set to `null` in Sprint 8:

```text
input_url
normalized_url
final_url
```

`03_candidate_urls.jsonl` does not carry these fields — they come from Stage 00/01 and are not passed forward. Set them to `null` now so the schema is stable when a future sprint passes richer records forward.

Example:

```json
{
  "source_lead_id": "lead_1",
  "source_url": "https://apex.example/",
  "input_url": null,
  "normalized_url": null,
  "final_url": null,
  "generated_at": "2026-05-17T13:40:00Z"
}
```

---

# Output Record Contract

Write:

```text
04_markdown_pages.jsonl
```

Each line must be one JSON object.

Each output record should satisfy:

```python
MARKDOWN_PAGE_REQUIRED
```

Required fields:

```text
run_id
source_lead_id
candidate_url
candidate_type
fetch_status
markdown_path
markdown_filename
generated_at
```

Recommended additional fields:

```text
candidate_score
http_status
content_type
content_hash
```

Example output record:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "candidate_url": "https://apex.example/vendors",
  "candidate_type": "vendor_page",
  "candidate_score": 80,
  "fetch_status": "fetched",
  "http_status": 200,
  "content_type": "text/html",
  "markdown_path": "generated_wiki/lead_1/vendors.md",
  "markdown_filename": "vendors.md",
  "content_hash": "sha256:abc123",
  "generated_at": "2026-05-17T13:40:00Z"
}
```

`markdown_path` should be relative to the run folder, not absolute.

---

# Fetch Status Values

Allowed `fetch_status` values for v1:

```text
fetched
non_html
fetch_error
timeout
```

## Routing Table

Every selected candidate produces an output record. The table below defines what else is written per outcome:

| Outcome | Output record | `markdown_path` / `markdown_filename` / `content_hash` | Error record | `pages_failed` | `non_html_count` |
|---|---|---|---|---|---|
| `fetched` | yes | real values | no | — | — |
| `non_html` | yes | `null` | no | — | +1 |
| `timeout` | yes | `null` | yes (`retryable=true`) | +1 | — |
| `fetch_error` | yes | `null` | yes (`retryable=true`) | +1 | — |
| malformed input | no | — | yes (`retryable=false`) | — | — |

For output records where no markdown was written, set `markdown_path`, `markdown_filename`, and `content_hash` to `null`. The `MARKDOWN_PAGE_REQUIRED` contract checks field presence, not non-null values.

Writing an output record for every selected candidate (including failures) keeps the summary arithmetic consistent: `selected_candidates == output_records + malformed_skipped`.

## `fetched`

The URL returned a successful HTML response and markdown was written.

## `non_html`

The URL returned a non-HTML response. Write an output record with `fetch_status = non_html`. Do not write a markdown file. Do not write an error record.

## `timeout`

The fetcher raised `FetchTimeoutError`. Write an output record with `fetch_status = timeout` and an error record with `retryable = true`.

## `fetch_error`

The fetcher raised a generic exception. Write an output record with `fetch_status = fetch_error` and an error record with `retryable = true`.

---

# Error Artifact Contract

Write:

```text
04_markdown_pages_errors.jsonl
```

Use this for failed candidate fetches, markdown conversion failures, malformed input records, or unexpected errors.

Required fields:

```text
run_id
stage_name
source_lead_id
candidate_url
error_type
message
retryable
created_at
```

Example:

```json
{
  "run_id": "test-run",
  "stage_name": "generate_markdown_pages",
  "source_lead_id": "lead_1",
  "candidate_url": "https://apex.example/vendors",
  "error_type": "fetch_failed",
  "message": "Request timed out",
  "retryable": true,
  "created_at": "2026-05-17T13:40:00Z"
}
```

A failed candidate should not crash the whole stage. Record the error and continue.

---

# Summary Artifact Contract

Write:

```text
04_markdown_pages_summary.json
```

Required fields:

```text
stage_name
stage_number
input_records
selected_candidates
skipped_candidates
pages_fetched
pages_failed
non_html_count
markdown_files_written
lead_folders_created
error_records
started_at
completed_at
```

Example:

```json
{
  "stage_name": "generate_markdown_pages",
  "stage_number": "04",
  "input_records": 8,
  "selected_candidates": 4,
  "skipped_candidates": 4,
  "pages_fetched": 3,
  "pages_failed": 1,
  "non_html_count": 0,
  "markdown_files_written": 3,
  "lead_folders_created": 2,
  "error_records": 1,
  "started_at": "2026-05-17T13:40:00Z",
  "completed_at": "2026-05-17T13:40:02Z"
}
```

---

# StageResult Contract

The harness must return a JSON-serializable `StageResult`.

Example:

```json
{
  "stage_id": "04_generate_markdown_pages",
  "stage_number": "04",
  "stage_name": "generate_markdown_pages",
  "status": "completed",
  "consumed_artifacts": ["03_candidate_urls.jsonl"],
  "produced_artifacts": ["04_markdown_pages.jsonl"],
  "summary_artifact": "04_markdown_pages_summary.json",
  "error_artifact": "04_markdown_pages_errors.jsonl",
  "counts": {
    "input_records": 8,
    "selected_candidates": 4,
    "skipped_candidates": 4,
    "pages_fetched": 3,
    "pages_failed": 1,
    "non_html_count": 0,
    "markdown_files_written": 3,
    "lead_folders_created": 2,
    "error_records": 1
  },
  "started_at": "2026-05-17T13:40:00Z",
  "completed_at": "2026-05-17T13:40:02Z"
}
```

Artifact names should be relative filenames, not absolute paths.

---

# Hashing Rule

For successful markdown output, compute a content hash.

Suggested helper:

```python
compute_content_hash(markdown_text: str) -> str
```

Expected format:

```text
sha256:<hex_digest>
```

This should be deterministic and unit tested if not already tested.

---

# Required Tests

Create:

```text
tests/harness/test_generate_markdown_pages_stage.py
```

Use fake fetchers. Do not use real network.

## Test 1: writes standard artifacts

Given a valid `03_candidate_urls.jsonl`, running `run_generate_markdown_pages()` should create:

```text
04_markdown_pages.jsonl
04_markdown_pages_summary.json
04_markdown_pages_errors.jsonl
```

## Test 2: processes only selected candidates

Given selected, rejected, and external-reference records:

Expected:

```text
only selected records are fetched
skipped_candidates count includes non-selected records
```

## Test 3: writes markdown under generated_wiki/{source_lead_id}

Given:

```text
source_lead_id = lead_1
candidate_type = vendor_page
```

Expected file:

```text
generated_wiki/lead_1/vendors.md
```

## Test 4: writes lead_metadata.json

Given selected records for `lead_1`, expected:

```text
generated_wiki/lead_1/lead_metadata.json
```

exists and contains:

```text
source_lead_id
source_url
generated_at
```

## Test 5: HTML is converted to markdown

Given fake HTML:

```html
<h1>Vendors</h1>
<ul>
  <li>Smith Farm - vegetables and eggs</li>
</ul>
```

Expected markdown contains:

```text
Vendors
Smith Farm - vegetables and eggs
Source: <candidate_url>
```

## Test 6: output records satisfy MARKDOWN_PAGE_REQUIRED

For every output record:

```python
require_fields(record, MARKDOWN_PAGE_REQUIRED)
```

## Test 7: filename collisions do not overwrite

Given two selected `vendor_page` records for the same `source_lead_id`, expected files:

```text
vendors.md
vendors-2.md
```

Both files should exist.

## Test 8: non-HTML response records error and continues

Given selected candidate URL returns:

```text
content_type = application/pdf
```

Expected:

```text
no markdown file written
error or non_html status recorded
summary non_html_count increments
stage continues
```

## Test 9: fetch failure records error and continues

Fake fetcher raises exception.

Expected:

```text
error record is written
pages_failed increments
stage continues
```

## Test 10: StageResult is JSON-serializable

After running stage:

```python
json.dumps(result.to_dict())
```

should not raise.

## Test 11: stage writes only to provided StagePaths and generated_wiki under run dir

Use `StagePaths.for_stage()`.

Assert output artifacts are written to:

```text
paths.output_path
paths.summary_path
paths.errors_path
```

Assert generated wiki output is under the same run directory.

## Test 12: stage does not read market_registry.jsonl

Do not require or use any registry file.

---

# Boundaries

Do not implement:

- full orchestrator
- manifest updates
- real internet smoke test
- farmles_wiki import
- market identity
- Git/GitHub
- SQL export
- LLM extraction

Sprint 8 is only:

```text
Stage 04 generate_markdown_pages harness
generated_wiki/lead_N output
harness tests
```

---

# Acceptance Criteria

Sprint 8 is complete when:

1. `run_generate_markdown_pages()` is implemented.
2. It reads `03_candidate_urls.jsonl`.
3. It processes only `candidate_status = selected`.
4. It uses an injected fetcher.
5. It converts HTML to markdown using Sprint 7 converter logic.
6. It writes markdown files under `generated_wiki/{source_lead_id}/`.
7. It writes `lead_metadata.json` for each source lead.
8. It writes `04_markdown_pages.jsonl`.
9. It writes `04_markdown_pages_summary.json`.
10. It writes `04_markdown_pages_errors.jsonl`.
11. It returns a JSON-serializable `StageResult`.
12. Output records satisfy `MARKDOWN_PAGE_REQUIRED`.
13. Harness tests cover selected/skipped candidates, markdown writing, metadata writing, filename collisions, non-HTML responses, fetch errors, and StageResult serialization.
14. No real network calls are used in tests.
15. Existing Stage 00, 01, 02, and 03 tests still pass.
16. No orchestrator or wiki import logic is added.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Stage 04 harness implemented.
3. Tests added.
4. Test command used.
5. Test result.
6. Any assumptions or deferred work.
