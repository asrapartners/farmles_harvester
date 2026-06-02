# Score Candidate Pages Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

The `score_candidate_urls` stage takes discovered link records and decides which links are likely worth fetching in a later stage.

This stage answers:

> Which discovered links look useful enough to become candidate pages?

It uses deterministic, rule-based scoring.

It does **not** fetch pages.  
It does **not** validate whether discovered URLs return 200.  
It does **not** extract farmers market facts.  
It does **not** call an LLM.

---

## Stage Name

```text
score_candidate_urls
```

## Stage Number

```text
03
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
03_candidate_urls.jsonl
   ↓
04_fetched_candidate_urls.jsonl
```

---

## Consumed Artifact

```text
02_discovered_links.jsonl
```

Each input record represents one link discovered on a validated source page.

Example input record:

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

---

## Produced Artifacts

```text
03_candidate_urls.jsonl
03_candidate_urls_summary.json
03_candidate_urls_errors.jsonl
```

---

## Core Responsibility

For each discovered link record:

1. Read `discovered_url`, `link_text`, `is_internal`, and `follow_allowed`.
2. Apply deterministic scoring rules.
3. Assign a `candidate_score`.
4. Assign a `candidate_type`.
5. Assign a `candidate_status`.
6. Record `score_reasons`.
7. Write selected and optionally rejected candidate records to `03_candidate_urls.jsonl`.
8. Write structured errors to `03_candidate_urls_errors.jsonl`.
9. Write stage summary to `03_candidate_urls_summary.json`.
10. Return a serializable `StageResult`.

---

## Non-Responsibilities

This stage must not:

- fetch discovered URLs
- validate whether discovered URLs work
- parse HTML pages
- convert HTML to markdown
- extract market name
- extract market hours
- extract location
- extract vendors
- call an LLM
- crawl external domains
- update `manifest.json` directly

---

## Naming Note

The preferred stage name is:

```text
score_candidate_urls
```

Avoid naming this stage:

```text
store_candidates
```

Reason:

All stages store artifacts. This stage’s actual domain responsibility is scoring and selecting candidate pages.

---

## Input Filtering Rules

The stage may score all discovered link records, but it should only select records where:

```text
follow_allowed = true
is_internal = true
```

External links may be scored and recorded as rejected or external references, but they should not become fetch candidates in v1.

For v1:

```text
internal + follow_allowed = eligible for selection
external = record/reject, not selected for fetch
```

---

## Candidate Status Values

Allowed `candidate_status` values:

```text
selected
rejected
external_reference
```

### Meaning

```text
selected
```

The link is useful enough to be fetched by a later stage.

```text
rejected
```

The link does not appear useful enough for v1.

```text
external_reference
```

The link points to an external domain. It may be useful later, but it should not be fetched in this v1 candidate-page flow.

---

## Candidate Type Values

Allowed `candidate_type` values:

```text
vendor_page
hours_location_page
calendar_events_page
about_contact_page
general_market_page
external_reference
low_value_page
unknown
```

### Meaning

```text
vendor_page
```

Likely contains vendor names, vendor roster, product categories, or vendor applications.

```text
hours_location_page
```

Likely contains hours, schedule, address, directions, parking, or visit information.

```text
calendar_events_page
```

Likely contains calendar, events, seasonal dates, special markets, or opening days.

```text
about_contact_page
```

Likely contains about, contact, organization, manager, or general market info.

```text
general_market_page
```

Likely relevant to the market but not specific enough to classify more narrowly.

```text
external_reference
```

External link recorded as a reference, not a v1 fetch candidate.

```text
low_value_page
```

Clearly not useful for market data extraction.

```text
unknown
```

No strong positive or negative signal.

---

## Scoring Model

The scoring model should be deterministic and explainable.

Start with:

```text
score = 0
```

Then apply positive and negative rules.

The final score should be clamped to:

```text
0 <= candidate_score <= 100
```

---

## Positive Scoring Rules

### Vendor signals

If URL path contains one of:

```text
vendor
vendors
our-vendors
vendor-list
vendor-roster
```

Add:

```text
+40
```

Reason:

```text
url_contains_vendor
```

If link text contains one of:

```text
vendor
vendors
our vendors
```

Add:

```text
+30
```

Reason:

```text
link_text_contains_vendor
```

---

### Hours / schedule signals

If URL path contains one of:

```text
hours
schedule
when
season
open
```

Add:

```text
+35
```

Reason:

```text
url_contains_hours_schedule
```

If link text contains one of:

```text
hours
schedule
when
season
open
```

Add:

```text
+25
```

Reason:

```text
link_text_contains_hours_schedule
```

---

### Location / visit signals

If URL path contains one of:

```text
visit
location
directions
parking
map
maps
find-us
```

Add:

```text
+35
```

Reason:

```text
url_contains_location_visit
```

If link text contains one of:

```text
visit
location
directions
parking
map
find us
```

Add:

```text
+25
```

Reason:

```text
link_text_contains_location_visit
```

---

### Calendar / event signals

If URL path contains one of:

```text
calendar
events
event
opening-day
special-events
market-dates
```

Add:

```text
+30
```

Reason:

```text
url_contains_calendar_events
```

If link text contains one of:

```text
calendar
events
event
opening day
market dates
```

Add:

```text
+20
```

Reason:

```text
link_text_contains_calendar_events
```

---

### About / contact signals

If URL path contains one of:

```text
about
contact
info
faq
market-info
```

Add:

```text
+20
```

Reason:

```text
url_contains_about_contact
```

If link text contains one of:

```text
about
contact
info
faq
```

Add:

```text
+15
```

Reason:

```text
link_text_contains_about_contact
```

---

### General farmers market signals

If URL path or link text contains one of:

```text
market
farmers-market
farmers
```

Add:

```text
+15
```

Reason:

```text
contains_market_signal
```

---

### Internal link signal

If:

```text
is_internal = true
follow_allowed = true
```

Add:

```text
+10
```

Reason:

```text
internal_follow_allowed
```

---

## Negative Scoring Rules

### Obvious low-value pages

If URL path contains one of:

```text
privacy
privacy-policy
terms
terms-of-service
cookies
cookie-policy
accessibility
login
signin
sign-in
register
cart
checkout
account
wp-admin
feed
rss
```

Subtract:

```text
-100
```

Reason:

```text
url_contains_low_value_path
```

---

### Blog / archive penalty

If URL path contains one of:

```text
blog
news
post
posts
archive
archives
tag
category
author
```

Subtract:

```text
-25
```

Reason:

```text
url_contains_blog_archive_signal
```

Note:

A blog page may still be useful in rare cases, so this is a penalty, not always an automatic rejection unless the final score falls below threshold.

---

### Old year penalty

If URL path or link text contains a year older than the current year by more than one year, subtract:

```text
-30
```

Reason:

```text
contains_old_year
```

Example in 2026:

```text
2018
2019
2020
2021
2022
2023
2024
```

Note:

The current year should be provided in config or derived from runtime.

---

### COVID / stale operational content

If URL path or link text contains:

```text
covid
coronavirus
pandemic
```

Subtract:

```text
-25
```

Reason:

```text
contains_covid_stale_signal
```

---

### External link penalty

If:

```text
is_internal = false
```

Set:

```text
candidate_status = external_reference
candidate_type = external_reference
```

and do not select for v1 fetch.

Reason:

```text
external_link_not_selected_v1
```

External links may still be recorded in the output artifact if configured.

---

## Selection Thresholds

Default thresholds:

```json
{
  "selected_threshold": 40,
  "strong_candidate_threshold": 70
}
```

Candidate status rules:

```text
if is_internal = false:
  candidate_status = external_reference

else if follow_allowed = false:
  candidate_status = rejected

else if candidate_score >= selected_threshold:
  candidate_status = selected

else:
  candidate_status = rejected
```

Candidate strength may be derived:

```text
candidate_score >= 70      strong
40 <= candidate_score < 70 medium
candidate_score < 40       weak
```

---

## Candidate Type Assignment

Candidate type should be assigned based on strongest signal family.

Priority order if multiple categories match:

```text
1. vendor_page
2. hours_location_page
3. calendar_events_page
4. about_contact_page
5. general_market_page
6. low_value_page
7. unknown
```

Example:

```text
/vendors
→ vendor_page
```

Example:

```text
/visit-us
→ hours_location_page
```

Example:

```text
/events
→ calendar_events_page
```

Example:

```text
/privacy-policy
→ low_value_page
```

---

## Output Policy

For v1, write all scored records to `03_candidate_urls.jsonl`, including rejected records.

Reason:

This makes tuning easier because developers can inspect why links were rejected.

Each output record should clearly state:

```text
candidate_status
candidate_score
candidate_type
score_reasons
```

Later, if storage volume becomes a problem, rejected records may be moved to a separate diagnostics artifact.

---

## Deduplication Rule

Deduplicate candidate records by:

```text
source_lead_id + discovered_url
```

If duplicate records are present in input, keep the highest scoring result.

If scores tie, keep the first record.

---

## Output Record Contract

Each line in `03_candidate_urls.jsonl` must be one JSON object.

Required fields:

```text
run_id
source_lead_id
source_url
discovered_url
link_text
is_internal
follow_allowed
candidate_score
candidate_type
candidate_status
candidate_strength
score_reasons
scored_at
```

Optional fields:

```text
site_id
source_domain
discovered_domain
raw_href
depth
discovery_method
```

Example selected vendor page:

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
  "candidate_score": 80,
  "candidate_type": "vendor_page",
  "candidate_status": "selected",
  "candidate_strength": "strong",
  "score_reasons": [
    "url_contains_vendor",
    "link_text_contains_vendor",
    "internal_follow_allowed"
  ],
  "scored_at": "2026-05-16T11:55:00Z"
}
```

Example rejected low-value page:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000001",
  "source_url": "https://www.apexfarmersmarket.com/",
  "raw_href": "/privacy-policy",
  "discovered_url": "https://www.apexfarmersmarket.com/privacy-policy",
  "link_text": "Privacy Policy",
  "is_internal": true,
  "follow_allowed": true,
  "candidate_score": 0,
  "candidate_type": "low_value_page",
  "candidate_status": "rejected",
  "candidate_strength": "weak",
  "score_reasons": [
    "url_contains_low_value_path"
  ],
  "scored_at": "2026-05-16T11:55:00Z"
}
```

Example external reference:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000001",
  "source_url": "https://www.apexfarmersmarket.com/",
  "raw_href": "https://www.facebook.com/apexfarmersmarket",
  "discovered_url": "https://www.facebook.com/apexfarmersmarket",
  "discovered_domain": "facebook.com",
  "link_text": "Facebook",
  "is_internal": false,
  "follow_allowed": false,
  "candidate_score": 0,
  "candidate_type": "external_reference",
  "candidate_status": "external_reference",
  "candidate_strength": "weak",
  "score_reasons": [
    "external_link_not_selected_v1"
  ],
  "scored_at": "2026-05-16T11:55:00Z"
}
```

---

## Error Artifact Contract

`03_candidate_urls_errors.jsonl` is for unexpected processing failures.

Each error record must include:

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

Example:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "stage_name": "score_candidate_urls",
  "source_lead_id": "lead_000017",
  "discovered_url": "https://examplemarket.org/vendors",
  "error_type": "unexpected_scoring_error",
  "message": "Unexpected scoring failure",
  "retryable": false,
  "created_at": "2026-05-16T11:57:00Z"
}
```

Malformed input records should produce an error record and not crash the entire stage.

---

## Summary Artifact Contract

`03_candidate_urls_summary.json` must contain one JSON object.

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
vendor_page_count
hours_location_page_count
calendar_events_page_count
about_contact_page_count
general_market_page_count
low_value_page_count
unknown_count
started_at
completed_at
```

Example:

```json
{
  "stage_name": "score_candidate_urls",
  "stage_number": "03",
  "input_records": 1440,
  "output_records": 1440,
  "error_records": 2,
  "selected_count": 220,
  "rejected_count": 1030,
  "external_reference_count": 190,
  "strong_candidate_count": 90,
  "medium_candidate_count": 130,
  "weak_candidate_count": 1220,
  "vendor_page_count": 70,
  "hours_location_page_count": 95,
  "calendar_events_page_count": 35,
  "about_contact_page_count": 50,
  "general_market_page_count": 20,
  "low_value_page_count": 980,
  "unknown_count": 190,
  "started_at": "2026-05-16T11:50:00Z",
  "completed_at": "2026-05-16T11:57:00Z"
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
  "stage_id": "03_score_candidate_urls",
  "stage_number": "03",
  "stage_name": "score_candidate_urls",
  "status": "completed",
  "consumed_artifacts": [
    "02_discovered_links.jsonl"
  ],
  "produced_artifacts": [
    "03_candidate_urls.jsonl"
  ],
  "summary_artifact": "03_candidate_urls_summary.json",
  "error_artifact": "03_candidate_urls_errors.jsonl",
  "counts": {
    "input_records": 1440,
    "output_records": 1440,
    "error_records": 2,
    "selected_count": 220,
    "rejected_count": 1030,
    "external_reference_count": 190
  },
  "started_at": "2026-05-16T11:50:00Z",
  "completed_at": "2026-05-16T11:57:00Z"
}
```

---

## Suggested Python Components

### Pure scoring function

```text
score_discovered_link(link_record, config) -> CandidateScore
```

This function should:

- inspect `discovered_url`
- inspect `link_text`
- inspect `is_internal`
- inspect `follow_allowed`
- compute `candidate_score`
- assign `candidate_type`
- assign `candidate_status`
- return `score_reasons`

It should not know about:

- JSONL
- manifest
- run folders
- stage paths
- file handles

---

### Stage harness

```text
run_score_candidate_urls(input_path, stage_paths, run_id, config) -> StageResult
```

The harness should:

1. Read `02_discovered_links.jsonl`.
2. Call `score_discovered_link()` per record.
3. Deduplicate candidate records by `source_lead_id + discovered_url`.
4. Write `03_candidate_urls.jsonl`.
5. Write `03_candidate_urls_errors.jsonl`.
6. Write `03_candidate_urls_summary.json`.
7. Return `StageResult`.

---

## Configuration

Recommended config values:

```json
{
  "selected_threshold": 40,
  "strong_candidate_threshold": 70,
  "write_rejected_records": true,
  "current_year": 2026
}
```

---

## Implementation Rules

1. Preserve `source_lead_id` from the input record.
2. Preserve `source_url` from the input record.
3. Preserve `discovered_url` from the input record.
4. Use deterministic rules only.
5. Do not call an LLM.
6. Do not fetch discovered URLs.
7. Do not validate whether discovered URLs work.
8. Do not convert HTML to markdown.
9. Do not extract market facts.
10. Always include `candidate_score`, `candidate_type`, `candidate_status`, and `score_reasons`.
11. Clamp score to the range 0 to 100.
12. External links must not be selected as v1 fetch candidates.
13. All timestamps must be ISO-8601 strings.
14. All output files must be valid JSON or JSONL.
15. The stage must not update `manifest.json` directly.

---

# Passing Criteria for Tester Agent

## Unit Tests for `score_discovered_link()`

### Test 1: vendor link gets selected

Given:

```json
{
  "discovered_url": "https://example.org/vendors",
  "link_text": "Vendors",
  "is_internal": true,
  "follow_allowed": true
}
```

Expected:

```text
candidate_status = selected
candidate_type = vendor_page
candidate_score >= 40
score_reasons includes url_contains_vendor
score_reasons includes link_text_contains_vendor
```

---

### Test 2: hours link gets selected

Given:

```json
{
  "discovered_url": "https://example.org/hours",
  "link_text": "Market Hours",
  "is_internal": true,
  "follow_allowed": true
}
```

Expected:

```text
candidate_status = selected
candidate_type = hours_location_page
candidate_score >= 40
```

---

### Test 3: visit/location link gets selected

Given:

```json
{
  "discovered_url": "https://example.org/visit-us",
  "link_text": "Visit Us",
  "is_internal": true,
  "follow_allowed": true
}
```

Expected:

```text
candidate_status = selected
candidate_type = hours_location_page
candidate_score >= 40
```

---

### Test 4: calendar/events link gets selected

Given:

```json
{
  "discovered_url": "https://example.org/events",
  "link_text": "Events",
  "is_internal": true,
  "follow_allowed": true
}
```

Expected:

```text
candidate_status = selected
candidate_type = calendar_events_page
candidate_score >= 40
```

---

### Test 5: about/contact link can be selected if score reaches threshold

Given:

```json
{
  "discovered_url": "https://example.org/contact",
  "link_text": "Contact",
  "is_internal": true,
  "follow_allowed": true
}
```

Expected:

```text
candidate_type = about_contact_page
candidate_score reflects about/contact positive rules
candidate_status depends on selected_threshold
```

---

### Test 6: privacy link gets rejected

Given:

```json
{
  "discovered_url": "https://example.org/privacy-policy",
  "link_text": "Privacy Policy",
  "is_internal": true,
  "follow_allowed": true
}
```

Expected:

```text
candidate_status = rejected
candidate_type = low_value_page
candidate_score = 0
score_reasons includes url_contains_low_value_path
```

---

### Test 7: old blog link is penalized

Given:

```json
{
  "discovered_url": "https://example.org/blog/2019-opening-day",
  "link_text": "Opening Day 2019",
  "is_internal": true,
  "follow_allowed": true
}
```

Expected:

```text
score_reasons includes url_contains_blog_archive_signal
score_reasons includes contains_old_year
candidate_score is lower than equivalent non-old non-blog event link
```

---

### Test 8: external link becomes external_reference

Given:

```json
{
  "discovered_url": "https://facebook.com/examplemarket",
  "link_text": "Facebook",
  "is_internal": false,
  "follow_allowed": false
}
```

Expected:

```text
candidate_status = external_reference
candidate_type = external_reference
candidate_score = 0
score_reasons includes external_link_not_selected_v1
```

---

### Test 9: score is clamped to 100

Given a link that matches many positive signals.

Expected:

```text
candidate_score <= 100
```

---

### Test 10: score is clamped to 0

Given a link with strong negative signals.

Expected:

```text
candidate_score >= 0
```

---

### Test 11: candidate strength is assigned

Given scores:

```text
80
50
10
```

Expected:

```text
80 -> strong
50 -> medium
10 -> weak
```

---

## Stage Harness Tests

### Test 12: reads discovered links and writes candidate pages

Given an input file with 3 discovered link records.

Expected:

```text
03_candidate_urls.jsonl exists
it contains scored records
each record contains candidate_score
each record contains candidate_type
each record contains candidate_status
each record contains score_reasons
```

---

### Test 13: preserves source identity

Given input:

```json
{
  "source_lead_id": "lead_000001",
  "source_url": "https://example.org/",
  "discovered_url": "https://example.org/vendors"
}
```

Expected output preserves:

```text
source_lead_id
source_url
discovered_url
```

---

### Test 14: deduplicates by source_lead_id + discovered_url

Given duplicate input records with the same:

```text
source_lead_id
discovered_url
```

Expected:

```text
only one output candidate record
```

---

### Test 15: writes summary JSON

After running the stage:

```text
03_candidate_urls_summary.json exists
```

Expected fields:

```text
stage_name = score_candidate_urls
stage_number = 03
input_records
output_records
selected_count
rejected_count
external_reference_count
started_at
completed_at
```

---

### Test 16: malformed input record goes to errors artifact

Given an input record missing `discovered_url`.

Expected:

```text
03_candidate_urls_errors.jsonl exists
error record includes error_type
stage does not crash
summary error_records increments
```

---

### Test 17: returns serializable StageResult

Expected:

```text
StageResult can be converted to dict
StageResult can be serialized to JSON
StageResult includes consumed_artifacts
StageResult includes produced_artifacts
StageResult includes counts
```

---

### Test 18: manifest is not updated by the stage

Expected:

```text
run_score_candidate_urls returns StageResult
stage itself does not directly modify manifest.json
```

The orchestrator owns manifest updates.

---

### Test 19: stage does not fetch URLs

Given input links.

Expected:

```text
no network fetch is attempted
```

This can be verified with mocks.

---

## Definition of Done

This stage is complete when:

1. The stage reads `02_discovered_links.jsonl`.
2. The stage scores each discovered link using deterministic rules.
3. The stage assigns `candidate_score`.
4. The stage assigns `candidate_type`.
5. The stage assigns `candidate_status`.
6. The stage records `score_reasons`.
7. The stage writes `03_candidate_urls.jsonl`.
8. The stage writes `03_candidate_urls_summary.json`.
9. The stage writes `03_candidate_urls_errors.jsonl`.
10. The stage returns a JSON-serializable `StageResult`.
11. Unit tests cover vendor, hours, visit/location, calendar/events, about/contact, privacy, old blog, external, score clamping, candidate strength, deduplication, and malformed input.
12. The stage does not fetch pages, validate URLs, extract facts, convert markdown, call an LLM, or update the manifest directly.

## Implementation

**Entry function:** `run_score_candidate_urls(input_path, stage_paths, run_id, config)`
[`stages/score_candidate_urls.py`](../../farmles_harvester/stages/score_candidate_urls.py)

Call sequence:
1. `stream_jsonl()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — streams discovered link records
2. `score_discovered_link(LinkRecord, config)` — local pure function — applies token-based scoring rules, returns `CandidateScore`
3. `JsonlWriter` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — writes all scored records (selected and rejected)

Key dataclasses (also imported by stage 02):
- `LinkRecord` — `(discovered_url, link_text, is_internal, follow_allowed)`
- `CandidateScore` — `(candidate_score, candidate_type, candidate_status, candidate_strength, score_reasons)`

Scoring constants: `CandidateType`, `CandidateStatus`, `CandidateStrength` in [`constants.py`](../../farmles_harvester/constants.py)

Input field contract: `DISCOVERED_LINK_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)
