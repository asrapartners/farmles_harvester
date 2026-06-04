# Real World Smoke Test Runbook

## Purpose

Run `farmles_harvester` against one real public farmers market URL and inspect the generated artifacts.

This runbook is for re-running the smoke test after Sprint 10 has already been implemented.

The goal is to confirm that the pipeline still works end-to-end against a real website.

---

## When to Use

Use this runbook when you want to manually verify:

- real URL fetching still works
- the full pipeline completes
- candidate links are selected reasonably
- markdown output is readable
- `generated_wiki/` output is created

Do not use this as a required CI test. Real websites can change or fail for reasons outside the codebase.

---

## Create Seed File

Create a temporary seed file:

```text
real_smoke_seed_urls.txt
```

Example:

```text
https://www.apexfarmersmarket.com/
```

Use only one URL for the smoke test.

---

## Run Command

```bash
farmles_harvester \
  --seed-file ./real_smoke_seed_urls.txt \
  --tag real-url-smoke
```

This should create a run folder like:

```text
runs/{timestamp}_real-url-smoke/
```

---

## Inspect the Run Folder

Open the newest run folder and inspect:

```text
manifest.json
00_normalized_source_leads.jsonl
01_validated_sources.jsonl
02_discovered_links.jsonl
03_candidate_urls.jsonl
04_markdown_pages.jsonl
generated_wiki/
```

---

## Pass Criteria

The smoke test passes if:

1. The pipeline completes without crashing.
2. `manifest.json` exists.
3. `01_validated_sources.jsonl` shows the URL as `valid` or `redirected`.
4. `02_discovered_links.jsonl` contains reasonable homepage links.
5. `03_candidate_urls.jsonl` selects useful candidate URLs.
6. `04_markdown_pages.jsonl` exists.
7. `generated_wiki/sources/{source_slug}/pages/` contains readable markdown files.
8. Markdown files include source URL footers.

---

## Review Checklist

### Stage 00: Normalize Source Leads

Check:

```text
00_normalized_source_leads.jsonl
```

Confirm:

- one input URL produced one source lead
- `normalized_url` looks correct
- `source_slug` exists and matches the seed URL domain

---

### Stage 01: Validate URLs

Check:

```text
01_validated_sources.jsonl
```

Confirm:

- `validation_status` is `valid` or `redirected`
- `final_url` is reasonable
- `http_status` is usually `200`
- `content_type` is HTML

---

### Stage 02: Discover Links

Check:

```text
02_discovered_links.jsonl
```

Confirm:

- reasonable links were discovered
- internal links are marked `is_internal = true`
- external links are marked `is_internal = false`
- discovered links were not fetched in this stage

Look for useful terms:

```text
vendors
visit
hours
events
contact
about
```

---

### Stage 03: Score Candidate URLs

Check:

```text
03_candidate_urls.jsonl
```

Confirm:

- useful links are selected
- privacy/terms/login pages are rejected
- external links are not selected for fetching
- `candidate_score` and `candidate_type` look reasonable

---

### Stage 04: Generate Markdown Pages

Check:

```text
04_markdown_pages.jsonl
generated_wiki/
```

Confirm:

- selected candidate URLs were fetched
- markdown files were created under `generated_wiki/sources/{source_slug}/pages/`
- `source_metadata.json` exists (stable fields only: source_slug, input_url, normalized_url, final_url)
- markdown is readable
- source URL footer exists
- obvious market facts are preserved

Example:

```text
generated_wiki/
  sources/
    apexfarmersmarket-com/
      source_metadata.json
      pages/
        vendors.md
        visit.md
```

---

## Write Smoke Test Notes

Create a file inside the run folder:

```text
smoke_test_notes.md
```

Use this template:

```md
# Smoke Test Notes

## Seed URL

<URL used>

## Run Folder

<run folder path>

## Result

Passed / Failed / Partial

## Observations

- 
- 
- 

## Issues

- 
- 
- 

## Recommended Next Actions

- 
- 
- 
```

---

## If the Run Fails

If the site is blocked, down, timed out, or returns unexpected content:

1. Do not immediately treat it as a code failure.
2. Record the failure in `smoke_test_notes.md`.
3. Try one alternate official farmers market URL.
4. If both fail, report the failures and stop.

Do not add complex retry logic or browser automation as part of this runbook.

---

## Important Boundary

This runbook is for manual validation only.

Unit tests should continue to use fake fetchers and controlled sample HTML.
