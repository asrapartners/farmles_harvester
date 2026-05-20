# Generate Markdown for lead

## Purpose
Read selected candidate URLs, fetch those pages and convert them to markdown. Keep the pages close enough to html to preseverve evidence, but clean enough for humans. Do not preserve junk because it was in HTML. For example ignore
- navigation menus
- footer links
- cookie banners
- social widgets
- tracking scripts.
- do not rewrite facts
- do not summarize
- do not invent clean surface


## Input Data Model

## Output Data Mode
Each generated lead folder must contain `lead_metadata.json`

### Example lead_metadata.json
An example
```
{
  "source_lead_id": "lead_1",
  "input_url": "https://www.apexfarmersmarket.com/",
  "normalized_url": "https://www.apexfarmersmarket.com/",
  "final_url": "https://www.apexfarmersmarket.com/",
  "generated_at": "2026-05-17T13:24:00Z"
}
```

Each line in `04_markdown_pages.jsonl` must be one JSON object
```
run_id
source_lead_id
candidate_url
candidate_type
candidate_score
fetch_status
http_status
content_type
markdown_path
markdown_filename
content_hash
generated_at
```

An example is 
```
{
  "run_id": "2026-05-17_132400_initial-import",
  "source_lead_id": "lead_1",
  "candidate_url": "https://www.apexfarmersmarket.com/vendors",
  "candidate_type": "vendor_page",
  "candidate_score": 80,
  "fetch_status": "fetched",
  "http_status": 200,
  "content_type": "text/html",
  "markdown_path": "generated_wiki/lead_1/vendors.md",
  "markdown_filename": "vendors.md",
  "content_hash": "sha256:abc123",
  "generated_at": "2026-05-17T13:24:00Z"
}
```



## Design Pattern

### Pure Focussed functions

#### Filename Rules
candidate_type_to_filename(candidate_type) -> str
Choose markdown filenames based on candidate_type. This gives the wiki a predictable structure. Generating filenames from URL paths gets messy.
```
general_market_page   → index.md
vendor_page           → vendors.md
hours_location_page   → visit.md
calendar_events_page  → events.md
about_contact_page    → about.md
unknown               → page-{n}.md
```
if 2 candidate URL's map to the same flename avoid overwriting.
Example
```
 vendors.md
 vendors_2.md
 vendors_3.md
```

#### Filename collisions
ensure_unique_filename(base_filename, used_filenames) -> str

#### Parsing
html_to_markdown(html, source_url) -> str

compute_content_hash(markdown_text) -> str
build_markdown_path(source_lead_id, filename) -> Path
build_lead_metadata(records_for_lead) -> dict


## Tester Requirements

### Unit Tests
Write unit tests for
- candidate_type_to_filename()
- filename collision handling
- html_to_markdown()

Write harness tests for
- Reading input leads
- Selecting only candidate_status = selected to be processed.
- Rejected candidates are skipped and counted.
- markdown files are written user "generated_wiki/<source_lead_id>
- `lead_metadata.json` is written once per lead folder.
- Fetch failrues are recorded as errors and donot crash the stage.

## Example Ouptut Structure
```
runs/2026-05-17_132400_initial-import/
  04_markdown_pages.jsonl
  04_markdown_pages_summary.json
  04_markdown_pages_errors.jsonl

  generated_wiki/
    lead_1/
      lead_metadata.json
      index.md
      vendors.md
      visit.md

    lead_2/
      lead_metadata.json
      index.md
      vendors.md
```
