# Sprint 12 Prompt: Source Output Structure Correction

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 12 only**.

This sprint implements the architecture correction from:

```text
Errata 001: Source Output Structure Correction
```

Earlier Stage 04 output used run-local lead folders:

```text
generated_wiki/lead_N/
```

This must be changed to stable source folders:

```text
generated_wiki/sources/{source_slug}/
```

This sprint updates the implementation and tests to use the corrected output structure.

---

# Goal

Change the exported wiki output structure from:

```text
generated_wiki/
  lead_1/
    lead_metadata.json
    vendors.md
    visit.md
```

to:

```text
generated_wiki/
  sources/
    apexfarmersmarket-com/
      source_metadata.json
      pages/
        vendors.md
        visit.md
```

The goal is to make crawler output match the stable `farmles_wiki/sources/` structure so Git can merge repeated crawler runs efficiently.

---

# Why This Sprint Exists

`lead_N` is run-local and unstable.

Example:

```text
Run A:
  lead_1 = https://www.apexfarmersmarket.com/

Run B:
  lead_1 = https://pcfma.org/
```

Therefore, `lead_N` must not be used as the exported folder identity.

The exported folder identity should be a stable source slug:

```text
sources/{source_slug}/
```

---

# Required Output Structure

Stage 04 should write:

```text
generated_wiki/
  sources/
    {source_slug}/
      source_metadata.json
      pages/
        *.md
```

Example:

```text
generated_wiki/
  sources/
    apexfarmersmarket-com/
      source_metadata.json
      pages/
        index.md
        vendors.md
        visit.md
```

For an aggregator:

```text
generated_wiki/
  sources/
    pcfma-org/
      source_metadata.json
      pages/
        index.md
        markets.md
```

---

# Source Slug Rule

Implement or reuse a helper to derive a stable `source_slug` from the source URL.

Suggested function:

```python
source_url_to_slug(url: str) -> str
```

Suggested location:

```text
farmles_harvester/web/url_utils.py
```

or:

```text
farmles_harvester/stages/generate_markdown_pages.py
```

Prefer `url_utils.py` if the helper is reusable.

## Examples

```text
https://www.apexfarmersmarket.com/
→ apexfarmersmarket-com

https://pcfma.org/
→ pcfma-org

https://www.facebook.com/apexfarmersmarket
→ facebook-com-apexfarmersmarket
```

## Suggested rules

- Parse the URL.
- Use hostname.
- Remove leading `www.`.
- Replace non-alphanumeric characters with `-`.
- Collapse repeated `-`.
- Strip leading/trailing `-`.
- Include path segments only when needed to distinguish social/profile URLs or non-root sources.
- Keep output lowercase.

Do not include timestamps or run IDs.

---

# Source Metadata Rule

Replace:

```text
lead_metadata.json
```

with:

```text
source_metadata.json
```

The file must contain stable values only.

Required fields:

```text
source_slug
input_url
normalized_url
final_url
```

Example:

```json
{
  "source_slug": "apexfarmersmarket-com",
  "input_url": "https://www.apexfarmersmarket.com/",
  "normalized_url": "https://www.apexfarmersmarket.com/",
  "final_url": "https://www.apexfarmersmarket.com/"
}
```

If `input_url`, `normalized_url`, or `final_url` is not available in the candidate records, set the value to `null`.

Do not include volatile fields.

Forbidden fields:

```text
generated_at
run_id
harvester_run_id
source_lead_id
timestamp
local_path
content_hash
```

These belong in run artifacts, not committed source evidence.

---

# Markdown Output Rule

Markdown files should now be written under:

```text
generated_wiki/sources/{source_slug}/pages/
```

Example:

```text
generated_wiki/sources/apexfarmersmarket-com/pages/vendors.md
```

Do not write markdown directly under:

```text
generated_wiki/sources/{source_slug}/
```

Do not write markdown under:

```text
generated_wiki/lead_N/
```

---

# Stage 04 Updates

Update:

```text
farmles_harvester/stages/generate_markdown_pages.py
```

The harness:

```python
run_generate_markdown_pages(...)
```

should still:

1. Read `03_candidate_urls.jsonl`.
2. Process only `candidate_status = selected`.
3. Fetch selected `candidate_url`.
4. Convert HTML to markdown.
5. Choose filename with `candidate_type_to_filename()`.
6. Handle filename collisions.
7. Write `04_markdown_pages.jsonl`.
8. Write summary JSON.
9. Write errors JSONL.
10. Return `StageResult`.

But the generated markdown destination changes from:

```text
generated_wiki/{source_lead_id}/{filename}
```

to:

```text
generated_wiki/sources/{source_slug}/pages/{filename}
```

---

# Output Record Contract Update

Update `04_markdown_pages.jsonl` records so:

```text
markdown_path
```

uses the new relative path.

Example:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "source_slug": "apexfarmersmarket-com",
  "candidate_url": "https://apex.example/vendors",
  "candidate_type": "vendor_page",
  "candidate_score": 80,
  "fetch_status": "fetched",
  "http_status": 200,
  "content_type": "text/html",
  "markdown_path": "generated_wiki/sources/apexfarmersmarket-com/pages/vendors.md",
  "markdown_filename": "vendors.md",
  "content_hash": "sha256:abc123",
  "generated_at": "2026-05-17T13:40:00Z"
}
```

It is okay for JSONL artifacts to contain `generated_at`.

But `.md` files and `source_metadata.json` should stay stable.

---

# Record Contract Update

If needed, update:

```text
farmles_harvester/models/record_contracts.py
```

For `MARKDOWN_PAGE_REQUIRED`, consider adding:

```text
source_slug
```

New suggested required fields:

```python
MARKDOWN_PAGE_REQUIRED = {
    "run_id",
    "source_lead_id",
    "source_slug",
    "candidate_url",
    "candidate_type",
    "fetch_status",
    "markdown_path",
    "markdown_filename",
    "generated_at",
}
```

If adding `source_slug` as required causes too much test churn, add it as optional first. But the preferred v1 contract is to require it for Stage 04 output.

---

# Tests to Update

Update existing Stage 04 harness tests:

```text
tests/harness/test_generate_markdown_pages_stage.py
```

## Required changes

Tests should no longer expect:

```text
generated_wiki/lead_1/vendors.md
```

They should expect:

```text
generated_wiki/sources/{source_slug}/pages/vendors.md
```

Example:

```text
generated_wiki/sources/apex-example/pages/vendors.md
```

depending on the slug helper.

---

# Required New Unit Tests

Add or update tests for `source_url_to_slug()`.

Suggested file:

```text
tests/unit/test_source_slug.py
```

## Test 1: simple official market domain

```text
https://www.apexfarmersmarket.com/
→ apexfarmersmarket-com
```

## Test 2: aggregator domain

```text
https://pcfma.org/
→ pcfma-org
```

## Test 3: Facebook profile URL

```text
https://www.facebook.com/apexfarmersmarket
→ facebook-com-apexfarmersmarket
```

## Test 4: trailing slash does not change slug

```text
https://pcfma.org
https://pcfma.org/
```

Expected same slug:

```text
pcfma-org
```

## Test 5: query string does not affect slug

```text
https://www.apexfarmersmarket.com/?utm_source=test
```

Expected:

```text
apexfarmersmarket-com
```

---

# Required Harness Tests

Update or add Stage 04 harness tests.

## Test 1: writes markdown under stable source slug path

Given candidate source URL:

```text
https://apex.example/
```

Expected markdown path:

```text
generated_wiki/sources/apex-example/pages/vendors.md
```

## Test 2: writes stable source_metadata.json

Expected:

```text
generated_wiki/sources/apex-example/source_metadata.json
```

The file should contain only:

```text
source_slug
input_url
normalized_url
final_url
```

It should not contain:

```text
generated_at
run_id
harvester_run_id
source_lead_id
timestamp
content_hash
```

## Test 3: filename collisions remain inside pages folder

Given two selected vendor pages for the same source slug:

Expected:

```text
generated_wiki/sources/apex-example/pages/vendors.md
generated_wiki/sources/apex-example/pages/vendors-2.md
```

## Test 4: markdown stability still passes

Existing Sprint 11 stability tests should still pass with the new path structure.

Repeated runs with same inputs should produce identical `.md` content.

## Test 5: output records satisfy updated `MARKDOWN_PAGE_REQUIRED`

If `source_slug` is added to the required contract, verify every Stage 04 output record includes it.

---

# Import / Git Rationale

This sprint prepares for `farmles_wiki` PRs.

The harvester run output can now be overlaid into `farmles_wiki`:

```bash
rsync -av runs/.../generated_wiki/ ../farmles_wiki/
```

This copies:

```text
generated_wiki/sources/apexfarmersmarket-com/...
```

into:

```text
farmles_wiki/sources/apexfarmersmarket-com/...
```

Git can now merge repeated crawler runs efficiently because source paths are stable.

---

# Non-Responsibilities

Do not implement:

- `farmles_wiki` import tool
- GitHub PR creation
- market candidate extraction
- market identity resolution
- `markets/` folder updates
- SQL export
- LLM extraction
- aggregator splitting

This sprint only corrects the harvester exported source evidence structure.

---

# Acceptance Criteria

Sprint 12 is complete when:

1. Stage 04 no longer writes `generated_wiki/lead_N/`.
2. Stage 04 writes `generated_wiki/sources/{source_slug}/pages/*.md`.
3. Stage 04 writes stable `source_metadata.json`.
4. `source_metadata.json` contains only stable fields.
5. `source_url_to_slug()` or equivalent helper exists.
6. Unit tests cover source slug generation.
7. Stage 04 harness tests expect the new structure.
8. Markdown stability tests still pass.
9. Output records include `source_slug`.
10. Existing earlier stage tests still pass.
11. No wiki import, PR creation, market resolution, or SQL export logic is added.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Source output structure changes made.
3. Source slug helper added.
4. Tests added or updated.
5. Test command used.
6. Test result.
7. Any assumptions or deferred work.
