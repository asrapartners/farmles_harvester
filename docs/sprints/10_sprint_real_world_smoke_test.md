# Sprint 10 Prompt: First Real-World Smoke Test

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 10 only**.

Previous sprints built and tested the local pipeline using fake fetchers and controlled inputs.

Sprint 10 should run the completed local pipeline against **one real public website** as a manual smoke test.

This sprint is not about adding major new features.  
This sprint is about proving the system can touch the real web safely and produce a reasonable `generated_wiki/` output.

---

# Goal

Run `farmles_harvester` on one real farmers market URL and inspect the output artifacts.

The goal is to answer:

```text
Can the pipeline run end-to-end against one real public website without crashing?
```

and:

```text
Are the generated artifacts and markdown output reasonable enough for v1?
```

---

# Important Testing Boundary

This is a **manual smoke test**, not a CI test.

Do not make this a required automated test.

Real websites can change or fail for reasons outside our control:

```text
network issues
server downtime
blocking
redirect changes
HTML changes
robots/rate limits
```

Automated tests should continue using fake fetchers.

---

# Suggested Real URL

Use one known simple farmers market site.

Example:

```text
https://www.apexfarmersmarket.com/
```

If this URL fails or is blocked, choose another simple official farmers market website.

Use only one seed URL for this sprint.

---

# Command

Create a temporary seed file:

```text
real_smoke_seed_urls.txt
```

Example:

```text
https://www.apexfarmersmarket.com/
```

Run:

```bash
farmles_harvester \
  --seed-file ./real_smoke_seed_urls.txt \
  --tag real-url-smoke
```

Expected run folder:

```text
runs/{timestamp}_real-url-smoke/
```

---

# Expected Pipeline Flow

```text
real_smoke_seed_urls.txt
   ↓
farmles_harvester
   ↓
runs/{timestamp}_real-url-smoke/
   ↓
00_normalized_source_leads.jsonl
01_validated_sources.jsonl
02_discovered_links.jsonl
03_candidate_urls.jsonl
04_markdown_pages.jsonl
generated_wiki/
manifest.json
```

---

# Artifacts to Inspect

Inspect these files manually:

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

# Manual Review Checklist

## 1. Run folder

Verify:

```text
run folder was created
seed_urls.txt was copied into the run folder
manifest.json exists
all expected stage artifacts exist
```

## 2. Stage 00: normalized source leads

Inspect:

```text
00_normalized_source_leads.jsonl
```

Check:

```text
one input URL produced one normalized source lead
normalized_url looks correct
source_lead_id exists
```

## 3. Stage 01: validated sources

Inspect:

```text
01_validated_sources.jsonl
```

Check:

```text
validation_status is valid or redirected
final_url is reasonable
http_status is 200
content_type is HTML
```

If the site is blocked, timed out, or non-HTML, record that in the smoke test notes.

## 4. Stage 02: discovered links

Inspect:

```text
02_discovered_links.jsonl
```

Check:

```text
reasonable links were discovered from the homepage
internal links are marked internal
external links are marked external
discovered links were not fetched in this stage
```

Look for obvious useful links such as:

```text
vendors
visit
hours
events
contact
about
```

## 5. Stage 03: candidate URLs

Inspect:

```text
03_candidate_urls.jsonl
```

Check:

```text
useful links are selected
privacy/terms/login style links are rejected
external links are not selected for fetching
candidate_score and candidate_type look reasonable
```

## 6. Stage 04: markdown pages

Inspect:

```text
04_markdown_pages.jsonl
generated_wiki/
```

Check:

```text
selected candidate URLs were fetched
markdown files were created under generated_wiki/{source_lead_id}/
lead_metadata.json exists
markdown is readable
source URL footer exists
obvious market facts are preserved
```

Example generated structure:

```text
generated_wiki/
  lead_1/
    lead_metadata.json
    vendors.md
    visit.md
```

---

# Smoke Test Notes

Create a short report inside the run folder:

```text
smoke_test_notes.md
```

It should include:

```text
seed URL used
run folder path
date/time
overall result
what worked
what failed
issues found
recommended next actions
```

Example:

```md
# Smoke Test Notes

## Seed URL

https://www.apexfarmersmarket.com/

## Result

Pipeline completed successfully.

## Observations

- URL validated as redirected.
- Homepage links were discovered.
- Vendor and visit pages were selected.
- Markdown output was readable.
- Some navigation/footer content remained in markdown.

## Issues

- Candidate scoring selected one low-value page.
- Markdown contained extra menu text.

## Recommended Next Actions

- Tune candidate scoring rules.
- Consider later HTML cleanup if noise becomes common.
```

---

# What to Do if the Run Fails

If the real URL fails due to network or website behavior:

1. Do not treat that as a code failure immediately.
2. Record the failure in `smoke_test_notes.md`.
3. Try one alternate official farmers market URL.
4. If both fail, report the failure and stop.

Do not spend this sprint building complex retry logic or browser automation.

---

# Non-Responsibilities

Do not implement:

- new crawler depth
- advanced retry logic
- browser automation
- crawl4ai migration
- semantic cleanup
- LLM extraction
- farmles_wiki import
- SQL export
- Git/GitHub PR flow
- scheduler or background jobs

Sprint 10 is a real-world smoke test only.

---

# Acceptance Criteria

Sprint 10 is complete when:

1. A one-URL real smoke test was run.
2. A run folder was produced.
3. Expected stage artifacts were inspected.
4. `generated_wiki/` output was inspected if produced.
5. `smoke_test_notes.md` was written.
6. Any failures were recorded clearly.
7. No real-web smoke test was added as a required CI test.
8. No major new feature was added.

---

# Output Expected From Agent

When finished, report:

1. Seed URL used.
2. Run command used.
3. Run folder path.
4. Whether the pipeline completed.
5. Summary of artifacts produced.
6. Summary of generated markdown quality.
7. Issues found.
8. Recommended next sprint actions.
