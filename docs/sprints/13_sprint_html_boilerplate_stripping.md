# Sprint 13 Prompt: HTML Boilerplate Stripping

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 13 only**.

---

# Goal

Strip nav, footer, and repeated template chrome from fetched HTML *before* converting to markdown, so that generated wiki files contain only unique content and GitHub storage is not bloated with boilerplate.

---

# Why This Sprint Exists

Stage 04 currently passes raw HTML directly to `markdownify`. Every output `.md` file contains 50+ lines of identical nav/footer chrome scraped from the source site template. Across 420+ vendor files and 32+ market files this inflates GitHub storage significantly and pollutes wiki search results.

The fix is to strip boilerplate from HTML before conversion, using three algorithms applied in order of reliability.

---

# Algorithm Pipeline

Apply in this order on each fetched HTML page:

**Algorithm 3 — Multi-page hash frequency** (cross-page, strongest)

Split HTML text content into paragraph-level blocks. Hash each block. Count frequency across all pages fetched from the same source site. Any block present in ≥ 80% of pages is boilerplate — remove it before conversion.

Requires at least 3 pages from the same source to activate. Falls back gracefully to the remaining algorithms when fewer pages are available.

**Algorithm 1 — Semantic tag removal** (per-page, deterministic)

Remove elements by tag name: `<header>`, `<nav>`, `<footer>`, `<aside>`.

Also remove any element whose `id` or `class` attribute contains any of: `nav`, `header`, `footer`, `menu`, `sidebar`, `breadcrumb`.

**Algorithm 2 — Text/link density** (per-page, statistical fallback)

For each top-level block element, compute:

```
link_density = len(link text) / max(len(all text), 1)
text_density = len(stripped text) / max(len(all tags), 1)
```

Remove the block if `link_density > 0.5` AND `text_density < 0.3`.

---

# What to Build

## New file: `farmles_harvester/web/html_cleaner.py`

`html_utils.py` handles link extraction (crawl-time concern) and must not be modified. Boilerplate removal is a conversion-time concern and lives in its own module.

Implement four functions:

### `remove_semantic_boilerplate(html: str) -> str`

Algorithm 1. Uses BeautifulSoup. Removes:
- Tags: `header`, `nav`, `footer`, `aside`
- Any element with `id` or `class` containing: `nav`, `header`, `footer`, `menu`, `sidebar`, `breadcrumb`

Returns cleaned HTML string.

### `build_boilerplate_fingerprint(pages: list[str], threshold: float = 0.8, min_pages: int = 3) -> frozenset[str]`

Algorithm 3, step 1. Builds the fingerprint from a set of pages from the same source site.

- If `len(pages) < min_pages`, return `frozenset()` immediately.
- Split each page's text content into blocks by splitting on two or more consecutive newlines.
- Normalize each block: strip leading/trailing whitespace, collapse internal whitespace.
- Hash each normalized block with SHA-256 (hex digest).
- Count how many pages each hash appears in.
- Return the set of hashes present in `>= threshold` fraction of pages.

### `strip_fingerprinted_boilerplate(html: str, fingerprint: frozenset[str]) -> str`

Algorithm 3, step 2. Applies the fingerprint to a single page.

- If fingerprint is empty, return html unchanged.
- Parse with BeautifulSoup.
- For each block-level element (`div`, `section`, `ul`, `ol`, `nav`, `header`, `footer`, `aside`), compute the normalized text hash using the same normalization as `build_boilerplate_fingerprint`.
- If the hash is in the fingerprint, remove that element from the DOM.
- Return cleaned HTML string.

### `remove_low_density_blocks(html: str, max_link_density: float = 0.5, min_text_density: float = 0.3) -> str`

Algorithm 2. Removes top-level block elements that look like navigation by their text/link ratio.

- Parse with BeautifulSoup.
- For each direct child block element of `<body>`:
  - Compute `link_text = sum of text lengths of all <a> descendants`
  - Compute `total_text = len of all stripped text in element`
  - Compute `link_density = link_text / max(total_text, 1)`
  - If `link_density > max_link_density`, remove the element.
- Return cleaned HTML string.

---

## Modified: `farmles_harvester/stages/generate_markdown_pages.py`

Change `run_generate_markdown_pages` to a two-pass design within the existing function signature. No new stage, no new JSONL contract.

**Pass 1** — Fetch all HTML for the current run into memory, grouped by `source_lead_id`:

```
fetched_html: dict[str, str]           # candidate_url -> html text
source_html: dict[str, list[str]]      # source_lead_id -> [html, ...]
```

Build one fingerprint per source:

```
fingerprints: dict[str, frozenset[str]]  # source_lead_id -> fingerprint
```

**Pass 2** — For each candidate, apply the three algorithms in order before calling `html_to_markdown`:

```
html = fetched_html[candidate_url]
fingerprint = fingerprints[source_lead_id]
html = strip_fingerprinted_boilerplate(html, fingerprint)   # Algorithm 3
html = remove_semantic_boilerplate(html)                    # Algorithm 1
html = remove_low_density_blocks(html)                      # Algorithm 2
markdown = html_to_markdown(html, source_url)
```

Add two optional config keys (passed through the existing `config: dict` parameter):

```
boilerplate_threshold      float   default 0.8   passed to build_boilerplate_fingerprint
min_pages_for_fingerprint  int     default 3     passed to build_boilerplate_fingerprint
```

Import from `farmles_harvester.web.html_cleaner`.

The JSONL output record contract (`MARKDOWN_PAGE_REQUIRED`) does not change.

---

# New Unit Tests: `tests/unit/test_html_cleaner.py`

Write these tests **before** implementing the functions (TDD). All tests must pass before modifying Stage 04.

## `remove_semantic_boilerplate`

**test_strips_nav_tag**
Input: `<html><body><nav>menu</nav><main>content</main></body></html>`
Assert: output contains "content", does not contain "menu"

**test_strips_header_and_footer_tags**
Input: `<header>logo</header><article>story</article><footer>©</footer>`
Assert: "story" present, "logo" and "©" absent

**test_strips_element_by_class_name**
Input: `<div class="nav-menu">nav</div><div class="content">body</div>`
Assert: "body" present, "nav" absent

**test_strips_element_by_id**
Input: `<div id="main-header">header</div><div id="page-content">article</div>`
Assert: "article" present, "header" absent

**test_passes_clean_html_unchanged**
Input: `<html><body><h1>Title</h1><p>Text</p></body></html>`
Assert: both "Title" and "Text" present in output

## `build_boilerplate_fingerprint`

**test_identifies_block_present_in_all_pages**
Input: 5 pages, each containing the same nav block ("Menu A | Menu B | Menu C") plus unique body text
Assert: fingerprint contains the hash of the nav block text
Assert: fingerprint does not contain hashes of the unique body text

**test_returns_empty_for_single_page**
Input: 1 page, `min_pages=3` (default)
Assert: fingerprint is `frozenset()`

**test_returns_empty_for_fewer_than_min_pages**
Input: 2 pages, `min_pages=3`
Assert: fingerprint is `frozenset()`

**test_threshold_below_cutoff_excluded**
Input: 10 pages; one block appears in 6 of them (60%); threshold=0.8
Assert: that block's hash is not in fingerprint

**test_threshold_above_cutoff_included**
Input: 10 pages; one block appears in 9 of them (90%); threshold=0.8
Assert: that block's hash is in fingerprint

**test_unique_content_not_fingerprinted**
Input: 5 pages each with entirely unique body text, same nav block
Assert: none of the unique body block hashes appear in fingerprint

## `strip_fingerprinted_boilerplate`

**test_removes_fingerprinted_node**
Construct a fingerprint containing the hash of a known block.
Input HTML contains that block plus a unique block.
Assert: fingerprinted block text absent, unique block text present.

**test_preserves_non_fingerprinted_node**
Fingerprint does not contain the block's hash.
Assert: block text still present in output.

**test_empty_fingerprint_returns_html_unchanged**
Input: any HTML; fingerprint = `frozenset()`
Assert: output equals input.

## `remove_low_density_blocks`

**test_strips_link_only_block**
Input: `<body><div><a href="/1">L1</a><a href="/2">L2</a><a href="/3">L3</a></div><p>Real content paragraph with sufficient text.</p></body>`
Assert: "Real content paragraph" present; link-only div stripped.

**test_preserves_content_block**
Input: a `<p>` with 80 chars of prose text and one inline `<a>` link (link density well below 0.5)
Assert: block preserved.

**test_block_at_threshold_boundary**
Input: block where `link_density` equals exactly `max_link_density` (0.5)
Assert: block is preserved (threshold is exclusive: `> 0.5` triggers removal, `== 0.5` does not).

---

# New Harness Tests: `tests/harness/test_generate_markdown_pages_stage.py`

Add class `TestBoilerplateStripping`. Use `FakeFetcher` with inline HTML constants.

Define shared fixtures at the top of the class:

```python
SHARED_NAV = "<nav><a href='/a'>SiteMenuA</a><a href='/b'>SiteMenuB</a><a href='/c'>SiteMenuC</a></nav>"
SHARED_FOOTER = "<footer>Copyright ACME Corp. All rights reserved.</footer>"

VENDOR_1_HTML = f"<html><body>{SHARED_NAV}<main><h1>Farm Alpha</h1><p>Sells apples.</p></main>{SHARED_FOOTER}</body></html>"
VENDOR_2_HTML = f"<html><body>{SHARED_NAV}<main><h1>Farm Beta</h1><p>Sells honey.</p></main>{SHARED_FOOTER}</body></html>"
VENDOR_3_HTML = f"<html><body>{SHARED_NAV}<main><h1>Farm Gamma</h1><p>Sells eggs.</p></main>{SHARED_FOOTER}</body></html>"
```

All three pages share the same `source_lead_id` so Algorithm 3 activates.

**test_shared_nav_not_in_output_files**
Run stage with all three vendor pages from the same source.
Assert: no output `.md` file contains "SiteMenuA", "SiteMenuB", or "SiteMenuC".

**test_shared_footer_not_in_output_files**
Assert: no output `.md` file contains "Copyright ACME Corp".

**test_unique_content_preserved**
Assert: Farm Alpha's file contains "Sells apples", Farm Beta's contains "Sells honey", Farm Gamma's contains "Sells eggs".

**test_h1_vendor_name_preserved**
Assert: each file begins with the vendor name as an H1 heading (`# Farm Alpha`, etc.).

**test_source_url_footer_still_appended**
Regression: assert each file ends with `Source: {url}` (existing behaviour must not break).

**test_single_page_falls_back_to_semantic_stripping**
Run stage with only 1 page from a source (below `min_pages` threshold).
Use HTML with an explicit `<nav>` + `<main>`.
Assert: nav content absent in output (Algorithm 1 handled it), main content present.

**test_output_records_satisfy_contract**
Assert: `require_fields(record, MARKDOWN_PAGE_REQUIRED)` passes for every output record.

**test_summary_keys_present**
Assert: summary JSON still contains `selected_candidates` and `skipped_candidates` keys.

---

# Non-Responsibilities

Do not implement:

- A new pipeline stage or new JSONL contract
- Changes to `html_utils.py` (link extraction is a separate concern)
- Modifications to any stage other than Stage 04
- Markdown post-processing (stripping happens on HTML, before `markdownify`)
- LLM-based extraction or classification
- Any changes to the wiki output folder structure

---

# Acceptance Criteria

Sprint 13 is complete when:

1. `farmles_harvester/web/html_cleaner.py` exists with all four functions.
2. `tests/unit/test_html_cleaner.py` exists and all tests pass.
3. `TestBoilerplateStripping` harness tests all pass.
4. All existing Stage 04 harness tests still pass (no regressions).
5. All earlier stage tests still pass.
6. Running the pipeline against the PCFMA corpus produces `.md` files that do not contain the string `Main navigation`.
7. Running the pipeline against the PCFMA corpus produces `.md` files that do not contain the PCFMA footer copyright text.
8. Average markdown file size from the PCFMA run is reduced by at least 40% vs. the current run at `runs/2026-05-23_032337_aggregator-pcfma/generated_wiki/`.
9. Every vendor `.md` file still contains the vendor name as an H1 heading.
10. `html_utils.py` is not modified.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Which algorithms activated on the PCFMA corpus (was Algorithm 3 fingerprint built? how many blocks were fingerprinted?).
3. Tests added.
4. Test command used and result.
5. Before/after file size comparison for one sample vendor and one sample market file.
6. Any assumptions or deferred work.
