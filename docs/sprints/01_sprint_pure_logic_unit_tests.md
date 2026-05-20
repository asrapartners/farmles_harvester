# Sprint 1 Prompt: Pure Logic + Unit Tests

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 1 only**.

Do not implement the full pipeline harness yet.  
Do not build the orchestrator yet.  
Do not create run folders yet.  
Do not write JSONL stage artifacts yet.  
Do not fetch real websites.

Sprint 1 is about implementing and testing the **pure business logic functions** that later pipeline stages will use.

---

# Goal

Implement small, focused, testable functions for the early harvester pipeline.

The goal is:

```text
pure input
   ↓
pure logic function
   ↓
predictable output
```

No filesystem side effects except normal test files if needed.  
No real network calls.  
No Git.  
No GitHub.  
No SQL.  
No LLM.

---

# Context

Sprint 0 proved that the local tooling works:

- Python project setup
- pytest
- BeautifulSoup
- markdownify
- fake fetcher
- sample HTML

Sprint 1 now builds the core logic that future stages will wrap with harnesses.

Future pipeline:

```text
seed_urls.txt
   ↓
00_normalize_source_leads
   ↓
01_validate_urls
   ↓
02_discover_links
   ↓
03_score_candidate_urls
   ↓
04_generate_markdown_pages
```

Sprint 1 does **not** implement these stage harnesses. It only implements the pure logic functions those stages will later use.

---

# Required Design Principle

Separate pure logic from pipeline harness.

Pure logic functions must not know about:

- run folders
- manifest.json
- StagePaths
- StageResult
- JSONL artifact writing
- Git
- GitHub
- SQL
- real network calls

The functions should be easy to unit test with small strings, dicts, and generated HTML.

---

# Required Functions

Implement the following functions and unit tests.

You may choose internal implementation details, but keep the function names and responsibilities stable.

---

## 1. `normalize_url`

Suggested location:

```text
farmles_harvester/web/url_utils.py
```

Function:

```python
normalize_url(raw_url: str) -> NormalizedUrlResult
```

Purpose:

Convert messy human input into a clean, standard machine-readable URL.

Mental model:

```text
normalize = clean + standardize, not verify
```

This function does **not** check whether the URL works on the internet.

### Expected behavior

Examples:

```text
apexfarmersmarket.com
→ https://apexfarmersmarket.com/

https://www.localharvest.org/farmers-markets?utm_source=test
→ https://www.localharvest.org/farmers-markets

"  https://Example.com/Vendors#top  "
→ https://example.com/Vendors
```

### Suggested result model

Use a dataclass or simple object.

```python
@dataclass
class NormalizedUrlResult:
    input_url: str
    normalized_url: str | None
    status: str
    notes: list[str]
    error_message: str | None = None
```

Allowed status values:

```text
normalized
invalid_input
```

### Rules

- Trim whitespace.
- Add `https://` if the scheme is missing.
- Lowercase the domain.
- Do not blindly lowercase the path.
- Remove URL fragments.
- Remove common tracking query parameters such as:
  - `utm_source`
  - `utm_medium`
  - `utm_campaign`
  - `utm_term`
  - `utm_content`
  - `fbclid`
  - `gclid`
- Keep meaningful query parameters.
- For bare domains, add trailing slash.
- Reject malformed inputs that cannot become HTTP/HTTPS URLs.
- Do not check network reachability.

---

## 2. `parse_seed_lines`

Suggested location:

```text
farmles_harvester/stages/normalize_source_leads.py
```

Function:

```python
parse_seed_lines(seed_text: str) -> list[SourceLead]
```

Purpose:

Parse the user-provided seed file text into unique source lead records.

This function should use `normalize_url()`.

### Suggested result model

```python
@dataclass
class SourceLead:
    source_lead_id: str
    input_url: str
    normalized_url: str
    input_line: int
    normalization_notes: list[str]
```

### Expected behavior

Input:

```text
# NC markets

apexfarmersmarket.com
https://apexfarmersmarket.com/
https://www.localharvest.org/farmers-markets?utm_source=test
```

Output:

- skips comments
- skips blank lines
- deduplicates repeated normalized URLs
- assigns source lead IDs:
  - `lead_1`
  - `lead_2`
  - `lead_3`

### Rules

- Lines starting with `#` are comments and should be ignored.
- Blank lines should be ignored.
- Each remaining line is one candidate source lead.
- Duplicate normalized URLs should be discarded from the returned list.
- Do not create duplicate `SourceLead` objects for duplicate URLs.
- Do not fetch URLs.
- Do not write JSONL.

---

## 3. `extract_links_from_html`

Suggested location:

```text
farmles_harvester/web/html_utils.py
```

Function:

```python
extract_links_from_html(html: str, base_url: str) -> list[ExtractedLink]
```

Purpose:

Extract links from `<a href="...">...</a>` tags in an HTML page.

### Suggested result model

```python
@dataclass
class ExtractedLink:
    raw_href: str
    discovered_url: str
    link_text: str
```

### Expected behavior

Given:

```html
<a href="/vendors">Vendors</a>
<a href="/visit">Visit Us</a>
<a href="https://facebook.com/apexmarket">Facebook</a>
<a href="mailto:info@example.org">Email</a>
```

With base URL:

```text
https://apex.example/
```

Expected extracted web links:

```text
https://apex.example/vendors
https://apex.example/visit
https://facebook.com/apexmarket
```

`mailto:` should be ignored.

### Rules

- Extract only `<a href>` links.
- Resolve relative URLs using `base_url`.
- Preserve visible link text.
- Ignore empty hrefs.
- Ignore fragment-only hrefs like `#top`.
- Ignore JavaScript hrefs.
- Ignore `mailto:` hrefs.
- Ignore `tel:` hrefs.
- Do not fetch discovered links.
- Do not score discovered links.
- Do not write files.

---

## 4. `is_internal_link`

Suggested location:

```text
farmles_harvester/web/url_utils.py
```

Function:

```python
is_internal_link(source_url: str, discovered_url: str) -> bool
```

Purpose:

Decide whether a discovered URL belongs to the same website as the source URL.

### Expected behavior

```text
source_url = https://example.org/
discovered_url = https://example.org/vendors
→ True
```

```text
source_url = https://www.example.org/
discovered_url = https://example.org/vendors
→ True
```

```text
source_url = https://example.org/
discovered_url = https://facebook.com/example
→ False
```

### Rules

- Treat `www.example.org` and `example.org` as the same.
- For v1, compare normalized hostnames after removing leading `www.`.
- Do not implement complex public suffix logic unless already simple.
- Do not fetch URLs.

---

## 5. `score_discovered_link`

Suggested location:

```text
farmles_harvester/stages/score_candidate_urls.py
```

Function:

```python
score_discovered_link(link_record: dict, config: dict | None = None) -> CandidateScore
```

Purpose:

Use deterministic rules to score a discovered URL and decide whether it should become a candidate URL.

This function is rule-based, not AI-driven.

### Suggested result model

```python
@dataclass
class CandidateScore:
    candidate_score: int
    candidate_type: str
    candidate_status: str
    candidate_strength: str
    score_reasons: list[str]
```

Allowed candidate status values:

```text
selected
rejected
external_reference
```

Allowed candidate type values:

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

Candidate strength:

```text
strong
medium
weak
```

### Required scoring behavior

Vendor links should score high.

Example:

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
```

Privacy/terms/login pages should be rejected.

External links should become `external_reference`.

Old blog/archive links should be penalized.

### Suggested scoring rules

Positive signals:

```text
vendor, vendors, our-vendors
hours, schedule, season, open
visit, location, directions, parking, map
calendar, events, opening-day
about, contact, faq
market, farmers-market
```

Negative signals:

```text
privacy
terms
cookies
login
cart
checkout
wp-admin
feed
rss
tag
category
author
blog
archive
covid
```

Default thresholds:

```python
selected_threshold = 40
strong_candidate_threshold = 70
```

Clamp score:

```text
0 <= candidate_score <= 100
```

External link rule:

```text
if is_internal is false:
    candidate_status = external_reference
    candidate_type = external_reference
```

---

## 6. `candidate_type_to_filename`

Suggested location:

```text
farmles_harvester/stages/generate_markdown_pages.py
```

Function:

```python
candidate_type_to_filename(candidate_type: str) -> str
```

Purpose:

Map a candidate URL type to a standard markdown filename.

### Required mapping

```text
general_market_page   → index.md
vendor_page           → vendors.md
hours_location_page   → visit.md
calendar_events_page  → events.md
about_contact_page    → about.md
unknown               → page.md
```

This function does not handle filename collisions. It only maps type to base filename.

---

# Unit Test Requirements

Create unit tests under:

```text
tests/unit/
```

Recommended files:

```text
tests/unit/test_url_utils.py
tests/unit/test_seed_parsing.py
tests/unit/test_html_utils.py
tests/unit/test_score_candidate_urls.py
tests/unit/test_generate_markdown_pages_logic.py
```

Use existing helpers from Sprint 0:

```text
tests/helpers/html_factory.py
tests/helpers/fake_fetcher.py
```

---

## Required Tests for `normalize_url`

Test cases:

1. Adds `https://` when missing.
2. Trims whitespace.
3. Lowercases domain.
4. Does not lowercase path.
5. Removes URL fragment.
6. Removes tracking query params.
7. Keeps meaningful query params.
8. Adds trailing slash for bare domain.
9. Rejects malformed input.
10. Does not perform network access.

---

## Required Tests for `parse_seed_lines`

Test cases:

1. Skips blank lines.
2. Skips comment lines.
3. Assigns `lead_1`, `lead_2`, etc.
4. Preserves original input URL.
5. Stores normalized URL.
6. Preserves input line number.
7. Deduplicates duplicate normalized URLs.
8. Does not create duplicate records.

---

## Required Tests for `extract_links_from_html`

Test cases:

1. Extracts absolute links.
2. Resolves relative links.
3. Preserves link text.
4. Ignores empty href.
5. Ignores fragment-only href.
6. Ignores JavaScript href.
7. Ignores `mailto:`.
8. Ignores `tel:`.
9. Handles nested text inside anchor tags.

---

## Required Tests for `is_internal_link`

Test cases:

1. Same domain is internal.
2. `www` and non-`www` are treated as same.
3. Different domain is external.
4. Different subdomain is external for v1 unless it is only `www`.

---

## Required Tests for `score_discovered_link`

Test cases:

1. `/vendors` with text `Vendors` is selected as `vendor_page`.
2. `/visit` with text `Visit Us` is selected as `hours_location_page`.
3. `/events` with text `Events` is selected as `calendar_events_page`.
4. `/contact` gets `about_contact_page`.
5. `/privacy-policy` is rejected as `low_value_page`.
6. Old blog link is penalized.
7. External link becomes `external_reference`.
8. Score is clamped to 0 minimum.
9. Score is clamped to 100 maximum.
10. Candidate strength is assigned correctly.

---

## Required Tests for `candidate_type_to_filename`

Test cases:

1. `general_market_page` maps to `index.md`.
2. `vendor_page` maps to `vendors.md`.
3. `hours_location_page` maps to `visit.md`.
4. `calendar_events_page` maps to `events.md`.
5. `about_contact_page` maps to `about.md`.
6. Unknown/unsupported type maps to `page.md`.

---

# Important Boundaries

Do not implement:

- StagePaths
- StageResult
- orchestrator
- manifest.json
- JSONL writing
- stage harnesses
- real network fetching
- markdown page generation harness
- generated_wiki folder writing
- farmles_wiki import
- Git or GitHub
- SQL export
- LLM extraction

Sprint 1 is pure logic + unit tests only.

---

# Acceptance Criteria

Sprint 1 is complete when:

1. All required pure logic functions are implemented.
2. Unit tests exist for every required function.
3. All unit tests pass with `pytest`.
4. No real network calls are made.
5. No pipeline run folders are created.
6. No JSONL stage artifacts are written.
7. No orchestrator or stage harness is implemented.
8. Code remains small, explicit, and easy to test.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Functions implemented.
3. Unit tests added.
4. Test command used.
5. Test result.
6. Any assumptions or intentionally deferred work.
