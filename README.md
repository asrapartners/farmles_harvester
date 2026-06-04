# farmles_harvester

`farmles_harvester` is a the crawler and markdown generation tool for farmer market website.

It takes a user povided list of source URL's, runs them through a staged pipeline, and generates markdown files under a run folder.
The core data we care about:
- market name
- location
- opening days/hours
- seasonality
- vendors
- vendor products/categories

It does **not** own market identity, approved wiki content, Pull requests or SQL export. Those belong to `farmles_wiki` repo.

## High Level Flow

User provides a list of urls say in 'seed_urls.txt' to a cli script 'farmles_harvester`
    
```bash
  farmles_harvester --urls seed_urls.txt --tag initial-import
```

This creats under the "runs" folder a directory with name like "runs/{timestamp}_{tag}". For example "runs/2026-05-17-00_initial-import". This run folder contains all the JSON artifacts, a manifest and generated markdown files.

### Run Directory
```
runs/2026-05-17_132400_initial-import/
  seed_urls.txt
  manifest.json

  00_normalized_links.jsonl
  00_normalized_links_summary.json
  00_normalized_links_errors.jsonl

  01_validated_links.jsonl
  01_validated_links_summary.json
  01_validated_links_errors.jsonl

  02_discovered_links.jsonl
  02_discovered_links_summary.json
  02_discovered_links_errors.jsonl

  03_candidate_links.jsonl
  03_candidate_links_summary.json
  03_candidate_links_errors.jsonl

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
```

## Pipeline Stages
The script runs as a pipeline with each stage having a core responsibility. For each stage there is 
- stage name
- input artifact
- output artifact

### 00 Normalize Source Leads
Clean user provided URLs into normalized source lead records.

### 01 Validate URLs
Check whether the normalized URL's are reachable and record final RTL, HTTP status, content type and redirection.

- input `00_normalized_links.jsonl`
- output `01_validated_links.jsonl`

Refer to [01_validate_links](./docs/pipeline/01_validate_links.md) for more details

### 02 Discover Links
Fetch each validated source page and record links found in <a href="..."> tags.
Only discover level-1 links and does not fetch the discovered links.

- input `01_validated_links.jsonl`
- output `02_discovered_links.jsonl`

Refer to [02_discovered_links](./docs/pipeline/02_discovered_links.md) for more details

### 03 Score Candidate URLs
Use deterministic ruls to score discoved URLs and select URLs worth converting to markdown. This stage is rule based and not AI driven.

- input `02_discoverd_links.jsonl`
- output `03_candidate_links.jsonl`

Refer to [03_score_candidate_links](./docs/pipeline/03_candidate_links.md) for more details

## 04 Generate Markdown Pages
Fech selected candidate URLs and convert them to markdown files. The output is under 'generated_wiki' and organized by lead_id which is a simple incrementer.

- input `03_candidate_links.jsonl`
- output `04_markdown_pages.jsonl`, `generated_wiki/` for all the generated md files.

## Important Files
Each run has a manifest.json that holds the run ledger.
- run_id
- tag
- seed file snapshot
- stages executed
- artifacts produced
- errors
- execution log

---

## Developer Utilities

Installed commands (available after `pip install -e ".[dev]"`):

| Command | Purpose | Example |
|---|---|---|
| `detect_render <url>` | Detect whether a URL serves static HTML or a JS-rendered SPA (heuristic only, no pipeline stages) | `detect_render https://apexfarmersmarket.com --verbose` |
| `report_crawl` | Print a debugging report for a harvester run | `report_crawl --run runs/2026-05-17_132400_initial-import` |
| `scan_relevance <folder>` | Scan markdown files and report source relevance to farmer's markets | `scan_relevance generated_wiki/sources/` |

### Integration tests

`tests/integration/` contains tests that hit real URLs to verify pipeline stages end-to-end. They are excluded from the normal test run and must be triggered explicitly:

```bash
pytest -m integration
```

Each integration test file also works as a standalone debug utility:

```bash
python tests/integration/test_dynamic_detection.py https://apexfarmersmarket.com
python tests/integration/test_dynamic_detection.py https://some-spa.com --json
```

---

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

### 3. Install browser binaries for dynamic page crawling

```bash
crawl4ai-setup
```

> **Do you need to run this every time you clone?**  
> No. `crawl4ai-setup` installs Playwright browser binaries to a system-level path (`~/.cache/ms-playwright` on Linux/Mac). They persist across clones and only need to be re-run once per machine, or after upgrading `crawl4ai` to a version that requires a newer browser build. If you are unsure, run `crawl4ai-doctor` — it will tell you whether the setup is complete.

### 4. Verify

```bash
crawl4ai-doctor   # check browser setup
pytest            # all tests run offline, no network required
```

---

## Running the harvester

Create a plain-text file with one URL per line:

```
# seed_urls.txt
https://apexfarmersmarket.com
https://greenfieldfarmersmarket.org
```

Then run:

```bash
farmles_harvester --seed-file seed_urls.txt --tag initial-import
```

Output is written to `runs/{timestamp}_{tag}/`. For example:

```
runs/2026-05-17_132400_initial-import/
```

#### Common options

| Flag | Default | Purpose |
|------|---------|---------|
| `--tag TAG` | *(required)* | Label for this run, used in the folder name |
| `--runs-dir DIR` | `runs/` | Where to create the run folder |
| `--fast` | off | Skip URLs/pages that already have strong cached results |
| `--max-depth N` | 10 | Maximum link-discovery depth per source |
| `--registry-db PATH` | `{run_dir}/url_registry.db` | Reuse a registry from a previous run |

Full option reference: `farmles_harvester --help`

