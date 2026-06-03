# Generate Markdown Pages Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

The `generate_markdown_pages` stage takes selected candidate URLs, fetches each page, and converts it to clean markdown.

This stage answers:

> Which selected candidate pages contain market data worth preserving?

It keeps pages close enough to HTML to preserve evidence, but clean enough for humans.

It does **not** score or filter candidates.  
It does **not** rewrite facts.  
It does **not** summarize content.  
It does **not** invent clean surface.  
It does **not** preserve junk: navigation menus, footer links, cookie banners, social widgets, tracking scripts.

---

## Consumed Artifact

```text
03_candidate_urls.jsonl
```

Each input record represents one scored candidate URL from stage 03.

| Field | Required | How this stage uses it |
|---|---|---|
| `candidate_url` | yes | Fetched and converted to markdown |
| `candidate_status` | yes | Only `selected` records are processed |
| `candidate_type` | yes | Drives filename selection via `candidate_type_to_filename()` |
| `candidate_score` | yes | Preserved in output record |
| `source_slug` | yes | Derived from `source_url`; names the wiki folder under `generated_wiki/sources/` |
| `source_url` | yes | Preserved in output; used for slug derivation |
| `run_id` | yes | Validated; re-injected from harness `run_id` arg |
| `link_text` | no | Passed through if present |
| all other fields | no | Ignored |

---

## Core Responsibility

For each selected candidate record ([`stages/generate_markdown_pages.py`](../../farmles_harvester/stages/generate_markdown_pages.py) → `run_generate_markdown_pages()`):

1. Filter to `candidate_status = selected`; skip and count rejected records.
2. Derive the source folder name via `source_url_to_slug()` ([`web/url_utils.py`](../../farmles_harvester/web/url_utils.py)).
3. Assign a unique markdown filename via `candidate_type_to_filename()` and `ensure_unique_filename()` — local pure functions (`vendor_page` → `vendors.md`, `hours_location_page` → `visit.md`, etc.; see [Filename Rules](#filename-rules)).
4. Fetch the candidate page via `fetcher.fetch(candidate_url)` ([`web/fetcher.py`](../../farmles_harvester/web/fetcher.py)).
5. Detect render type via `detect_render_type()` ([`web/render_type_detector.py`](../../farmles_harvester/web/render_type_detector.py)) on the raw HTML — `static_html`, `dynamic_js`, or `unknown`. A weak markdown output combined with `dynamic_js` signals the page requires JavaScript to render its content.
6. Strip boilerplate via `clean_html()` ([`web/html_cleaner.py`](../../farmles_harvester/web/html_cleaner.py)).
7. Convert to markdown via `html_to_markdown()` — local helper.
8. Hash the markdown via `compute_content_hash()` — local helper.
9. Rate the markdown quality via `evaluate_markdown_strength()` ([`registry/evaluation.py`](../../farmles_harvester/registry/evaluation.py)) — assigns a strength signal used by the registry to decide whether re-fetching is worthwhile on future runs.
10. Write the markdown file under `generated_wiki/sources/<source_slug>/`, e.g. `generated_wiki/sources/apexfarmersmarket-com/vendors/index.md`.
11. Write `source_metadata.json` once per source folder after all pages for that source are written.
12. Append one record to `04_markdown_pages.jsonl` via `JsonlWriter` ([`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py)).

---

## Input Filtering Rules

Only records with `candidate_status = selected` are fetched.

Rejected and external records are skipped and counted in the summary but do not produce markdown output or error records.

---

## Output Data Model

Each generated source folder must contain `source_metadata.json`.

### Example source_metadata.json

```json
{
  "source_slug": "apexfarmersmarket-com",
  "input_url": "https://www.apexfarmersmarket.com/",
  "normalized_url": "https://www.apexfarmersmarket.com/",
  "final_url": "https://www.apexfarmersmarket.com/",
  "generated_at": "2026-05-17T13:24:00Z"
}
```

### Output Record Contract

Each line in `04_markdown_pages.jsonl` is one JSON object.

| Field | Required | Description |
|---|---|---|
| `run_id` | yes | Run identifier, injected by the harness |
| `source_slug` | yes | Identity of the seed lead; preserved from input |
| `source_url` | yes | Seed URL; preserved from input |
| `candidate_url` | yes | The fetched URL |
| `candidate_type` | yes | Signal family from stage 03 |
| `candidate_score` | yes | Score from stage 03 |
| `fetch_status` | yes | `fetched`, `fetch_failed`, or `skipped` |
| `http_status` | no | HTTP response code; absent on fetch failure |
| `content_type` | no | MIME type from response headers |
| `render_type` | no | `static_html`, `dynamic_js`, or `unknown`; detected from raw HTML before cleaning. `dynamic_js` with `markdown_strength = weak` indicates a JS-rendered page |
| `markdown_path` | no | Relative path to the written markdown file, e.g. `generated_wiki/sources/apexfarmersmarket-com/vendors/index.md`; absent on failure |
| `markdown_filename` | no | Filename only, e.g. `vendors.md`; absent on failure |
| `markdown_strength` | no | Quality rating of the converted markdown: `strong`, `medium`, or `weak`; absent on failure |
| `content_hash` | no | `sha256:<hex>`; absent on failure |
| `generated_at` | yes | ISO-8601 timestamp |

Example:

```json
{
  "run_id": "2026-05-17_132400_initial-import",
  "source_slug": "apexfarmersmarket-com",
  "candidate_url": "https://www.apexfarmersmarket.com/vendors",
  "candidate_type": "vendor_page",
  "candidate_score": 80,
  "fetch_status": "fetched",
  "http_status": 200,
  "content_type": "text/html",
  "markdown_path": "generated_wiki/sources/apexfarmersmarket-com/vendors/index.md",
  "markdown_filename": "vendors.md",
  "render_type": "static_html",
  "markdown_strength": "strong",
  "markdown_word_count": 412,
  "content_hash": "sha256:abc123",
  "generated_at": "2026-05-17T13:24:00Z"
}
```

---

## Output Policy

Write one record per selected candidate to `04_markdown_pages.jsonl`, including fetch failures.

Fetch failures set `fetch_status = fetch_failed` and do not include `markdown_path`, `markdown_filename`, or `content_hash`. They do not crash the stage.

`source_metadata.json` is written once per source folder after all candidates for that lead are processed.

Records with `candidate_status != selected` are skipped. They appear in the summary counts but not in the output JSONL.

---

## Error Artifact Contract

`04_markdown_pages_errors.jsonl` — one record per input the stage could not process.

| Field | Description |
|---|---|
| `run_id` | Run identifier |
| `stage_name` | Always `generate_markdown_pages` |
| `source_slug` | From the input record, if present |
| `candidate_url` | From the input record, if present |
| `error_type` | e.g. `fetch_error`, `invalid_input_record`, `write_error` |
| `message` | Human-readable description of the failure |
| `retryable` | Boolean |
| `created_at` | ISO-8601 timestamp |

---

## Summary Artifact Contract

`04_markdown_pages_summary.json` — one JSON object written after the stage completes.

| Field | Description |
|---|---|
| `stage_name` | `generate_markdown_pages` |
| `stage_number` | `04` |
| `run_id` | Run identifier |
| `input_records` | Total candidate records read |
| `selected_records` | Records with `candidate_status = selected` |
| `skipped_records` | Records with `candidate_status != selected` |
| `fetched_count` | Pages successfully fetched and converted |
| `fetch_failed_count` | Pages that failed to fetch |
| `error_records` | Records that failed processing for other reasons |
| `source_folders_created` | Number of distinct source folders written |
| `started_at` | ISO-8601 timestamp |
| `completed_at` | ISO-8601 timestamp |

---

## Design Pattern

### Pure Functions

#### Filename Rules

`candidate_type_to_filename(candidate_type) -> str`

Choose markdown filenames based on `candidate_type`. This gives the wiki a predictable structure. Generating filenames from URL paths gets messy.

```
general_market_page   → index.md
vendor_page           → vendors.md
hours_location_page   → visit.md
calendar_events_page  → events.md
about_contact_page    → about.md
unknown               → page-{n}.md
```

If two candidate URLs map to the same filename, avoid overwriting:

```
vendors.md
vendors_2.md
vendors_3.md
```

#### Filename Collisions

`ensure_unique_filename(base_filename, used_filenames) -> str`

#### Parsing

`html_to_markdown(html, source_url) -> str`

`compute_content_hash(markdown_text) -> str`

`build_markdown_path(source_slug, filename) -> Path`

`build_source_metadata(source_slug, records_for_source) -> dict`

---

## Example Output Structure

```
runs/2026-05-17_132400_initial-import/
  04_markdown_pages.jsonl
  04_markdown_pages_summary.json
  04_markdown_pages_errors.jsonl

  generated_wiki/
    sources/
      apexfarmersmarket-com/
        source_metadata.json
        index/index.md
        vendors/index.md
        visit/index.md

      localharvest-org/
        source_metadata.json
        index/index.md
        vendors/index.md
```

---

## Implementation

**Entry function:** `run_generate_markdown_pages(input_path, stage_paths, run_id, config, fetcher, registry)`
[`stages/generate_markdown_pages.py`](../../farmles_harvester/stages/generate_markdown_pages.py)

Call sequence:
1. `stream_jsonl()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — streams selected candidate records
2. `source_url_to_slug()` — [`web/url_utils.py`](../../farmles_harvester/web/url_utils.py) — derives folder name from source URL
3. `fetcher.fetch(candidate_url)` — [`web/fetcher.py`](../../farmles_harvester/web/fetcher.py) — fetches the candidate page
4. `detect_render_type()` — [`web/render_type_detector.py`](../../farmles_harvester/web/render_type_detector.py) — classifies raw HTML as `static_html`, `dynamic_js`, or `unknown`
5. `clean_html()` — [`web/html_cleaner.py`](../../farmles_harvester/web/html_cleaner.py) — strips boilerplate before conversion
6. `html_to_markdown()` — local helper — converts cleaned HTML to markdown
7. `compute_content_hash()` — local helper — SHA-256 hash of markdown content
8. `evaluate_markdown_strength()` — [`registry/evaluation.py`](../../farmles_harvester/registry/evaluation.py) — registry-based skip decision
9. `JsonlWriter` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — writes output artifact

Input field contract: `CANDIDATE_URL_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)

---

## Configuration

Recommended config values:

```json
{
  "fetch_timeout_seconds": 15,
  "max_retries": 2,
  "write_failed_records": true,
  "md_strong_min_words": 300,
  "md_medium_min_words": 100
}
```

---

## Test Requirements

### Unit Tests

- `candidate_type_to_filename()` — all known types and `unknown`
- Filename collision handling — `ensure_unique_filename()` with pre-populated sets
- `html_to_markdown()` — representative HTML with boilerplate elements

### Harness Tests

- Reading input leads from `03_candidate_urls.jsonl`
- Only `candidate_status = selected` records are processed
- Rejected candidates are skipped and counted
- Markdown files are written under `generated_wiki/sources/<source_slug>/`
- `source_metadata.json` is written once per source folder
- Fetch failures are recorded as errors and do not crash the stage

---

## Definition of Done

This stage is complete when:

1. The stage reads `03_candidate_urls.jsonl`.
2. Only `candidate_status = selected` records are fetched.
3. Rejected candidates are skipped and counted.
4. Each fetched page is cleaned and converted to markdown.
5. Markdown files are written under `generated_wiki/sources/<source_slug>/`.
6. `source_metadata.json` is written once per source folder.
7. The stage writes `04_markdown_pages.jsonl`.
8. Fetch failures are recorded as errors and do not crash the stage.
9. Unit tests cover `candidate_type_to_filename()`, filename collision handling, and `html_to_markdown()`.
10. Harness tests cover input reading, selection filtering, rejected-skipped counts, file writes, and fetch failures.
11. The stage does not score links, rewrite facts, summarize content, or call an LLM directly.
