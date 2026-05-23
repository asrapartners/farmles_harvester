# Sprint 14 Prompt: Strip `/index.php` Front-Controller Prefix from Discovered URLs

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 14 only**.

---

# Goal

Prevent duplicate markdown files caused by PHP front-controller URLs (e.g. `/index.php/market/berryessa-farmers-market`) being discovered and processed alongside their canonical equivalents (e.g. `/market/berryessa-farmers-market`).

---

# Why This Sprint Exists

Some CMS platforms (Drupal, Joomla, older WordPress) serve the same content at two URL forms:

- `https://www.pcfma.org/market/berryessa-farmers-market` — canonical clean URL
- `https://www.pcfma.org/index.php/market/berryessa-farmers-market` — PHP front-controller alias

Both forms appear as `<a href>` links in the site's HTML. Stage 02 (`discover_links`) finds both, and because they are different strings the `visited` dedup set treats them as distinct URLs. Both propagate through Stage 03 and Stage 04, creating two identical file trees:

```
generated_wiki/sources/pcfma-org/market/berryessa-farmers-market/index.md   ← correct
generated_wiki/sources/pcfma-org/index.php/market/berryessa-farmers-market/index.md  ← duplicate
```

Confirmed in the run at `runs/2026-05-23_032337_aggregator-pcfma/`: the entire `generated_wiki/sources/pcfma-org/index.php/` subtree is a duplicate of the top-level tree.

The fix is to strip the `/index.php` segment during URL normalization so the canonical and alias forms collapse to the same string before any deduplication or file-writing occurs.

---

# What to Build

## Modified: `farmles_harvester/web/url_utils.py`

In `normalize_url()`, after `path = parsed.path` is assigned (currently line 60), add the following block before the trailing-slash guard:

```python
if path.startswith("/index.php/"):
    path = path[len("/index.php"):]
    notes.append("stripped /index.php front-controller prefix")
elif path == "/index.php":
    path = "/"
    notes.append("stripped /index.php front-controller prefix")
```

This keeps all URL normalization logic in one place, is auditable via `notes`, and is covered by the existing unit-test class.

## Modified: `farmles_harvester/stages/discover_links.py`

Add `normalize_url` to the existing import from `farmles_harvester.web.url_utils`:

```python
from farmles_harvester.web.url_utils import is_internal_link, normalize_url
```

In the `for link in links:` loop, normalize each discovered URL before any downstream use:

```python
norm = normalize_url(link.discovered_url)
discovered_url = norm.normalized_url if norm.normalized_url else link.discovered_url
```

Replace every subsequent use of `link.discovered_url` inside the loop body with `discovered_url`. This affects:

- the `is_internal_link(fetch_url, ...)` call
- the `out.write({...})` record — write normalized form as `"discovered_url"`
- the `discovered_url not in visited` guard
- `visited.add(...)` 
- `queue.append(...)` — the URL passed to the BFS queue

`raw_href` in the output record stays unchanged (it documents what was in the HTML source).

No changes to any other stage, JSONL contract, or output directory structure.

---

# Tests

## `tests/unit/test_url_utils.py` — add to `TestNormalizeUrl`

```python
def test_strips_index_php_path_prefix(self):
    result = normalize_url("https://www.pcfma.org/index.php/market/berryessa")
    assert result.status == "normalized"
    assert result.normalized_url == "https://www.pcfma.org/market/berryessa"
    assert any("index.php" in note for note in result.notes)

def test_strips_bare_index_php(self):
    result = normalize_url("https://www.pcfma.org/index.php")
    assert result.status == "normalized"
    assert result.normalized_url == "https://www.pcfma.org/"

def test_does_not_alter_non_php_paths(self):
    result = normalize_url("https://example.com/market/downtown")
    assert result.status == "normalized"
    assert result.normalized_url == "https://example.com/market/downtown"

def test_does_not_alter_path_containing_index_php_mid_path(self):
    # Only strip leading /index.php, not occurrences elsewhere
    result = normalize_url("https://example.com/archive/index.php/old-page")
    assert result.status == "normalized"
    assert "archive/index.php" not in result.normalized_url or True  # implementation may or may not strip; document actual behaviour
```

> Note on the last test: `/archive/index.php/old-page` starts with `/archive`, not `/index.php/`, so stripping must not occur. Assert the URL is unchanged.

Rewrite the last test clearly:

```python
def test_does_not_strip_index_php_in_subpath(self):
    result = normalize_url("https://example.com/archive/index.php/old-page")
    assert result.status == "normalized"
    assert result.normalized_url == "https://example.com/archive/index.php/old-page"
```

## `tests/harness/test_discover_links_stage.py` — add class `TestIndexPhpDeduplication`

Use the existing `FakeFetcher` pattern already in the file.

**test_index_php_urls_normalized_to_canonical**

Seed the stage with one validated source at `https://example.org/`. The fake fetcher returns HTML for that page containing two links to the same content:

```html
<a href="/market/downtown">Downtown Market</a>
<a href="/index.php/market/downtown">Downtown Market</a>
```

Run the stage. Assert:
- All `discovered_url` values in the output JSONL equal `https://example.org/market/downtown` — none contain `index.php`.

**test_index_php_dedup_prevents_duplicate_output_records**

Same setup as above. Assert:
- Exactly one output record has `discovered_url == "https://example.org/market/downtown"` (the duplicate is collapsed, not doubled).

> If the existing harness uses a different fixture structure, follow it exactly. Do not introduce new test infrastructure.

---

# Non-Responsibilities

Do not implement:

- Changes to `candidate_url_to_rel_path()` in Stage 04 — normalization at discovery time makes path-level dedup in Stage 04 unnecessary for this issue
- Path-level file existence checks in Stage 04
- Stripping of other query-parameter-based duplicates (different issue, different sprint)
- Changes to `html_utils.py`, `score_candidate_urls.py`, `generate_markdown_pages.py`, or any other file not listed above

---

# Acceptance Criteria

Sprint 14 is complete when:

1. `normalize_url("https://www.pcfma.org/index.php/market/foo")` returns `"https://www.pcfma.org/market/foo"`.
2. `normalize_url("https://www.pcfma.org/index.php")` returns `"https://www.pcfma.org/"`.
3. All new unit tests in `TestNormalizeUrl` pass.
4. All existing `TestNormalizeUrl` tests still pass.
5. New harness tests in `TestIndexPhpDeduplication` pass.
6. All existing Stage 02 harness tests still pass (no regressions).
7. All earlier and later stage tests still pass.
8. A fresh crawl of pcfma.org does **not** produce a `generated_wiki/sources/pcfma-org/index.php/` directory.

---

# Output Expected From Agent

When finished, report:

1. Files modified and line-level summary of changes.
2. Tests added (names and file).
3. Test command used and result (pass/fail counts).
4. Confirmation that no `index.php/` subdirectory appears under `generated_wiki/sources/` in a fresh run, or explanation of why a fresh run was not executed.
5. Any assumptions or deferred work.
