# Sprint 7 Prompt: HTML to Markdown Converter Logic

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 7 only**.

Sprint 7 does **not** implement the full Stage 04 harness yet.

This sprint focuses only on the pure HTML-to-Markdown conversion logic that Stage 04 will later use.

---

# Goal

Implement and unit test a small, deterministic HTML-to-Markdown conversion utility.

The converter should produce markdown that is:

```text
faithful to the source HTML
lightly cleaned
easy for humans to review
usable later by farmles_wiki
```

The converter should not summarize, rewrite, or interpret the content.

---

# Scope

Implement:

```python
html_to_markdown(html: str, source_url: str) -> str
normalize_markdown(markdown: str) -> str
compute_content_hash(markdown_text: str) -> str
```

Location:

```text
farmles_harvester/stages/generate_markdown_pages.py
```

`candidate_type_to_filename()` already exists in this file from Sprint 1. Add the three functions above to the same file. Do not remove or replace `candidate_type_to_filename()`.

---

# Recommended Library

Use `markdownify`, which was already introduced in Sprint 0.

Expected approach:

```text
HTML
   ↓
markdownify
   ↓
normalize_markdown()
   ↓
append source URL footer
   ↓
markdown string
```

Do not use an LLM.

Do not build custom HTML parsing unless needed for the small contract below.

---

# Function: `html_to_markdown`

## Signature

```python
def html_to_markdown(html: str, source_url: str) -> str:
    ...
```

## Responsibility

Convert HTML into markdown and append the source URL.

The output should:

- preserve factual text
- preserve headings
- preserve lists
- preserve link text
- preserve useful links if `markdownify` naturally keeps them
- use consistent markdown heading style
- remove trailing whitespace
- collapse excessive blank lines
- append a source URL footer

## Source Footer

Every generated markdown string should include:

```md
---

Source: https://example.org/vendors
```

Use the actual `source_url` argument.

---

# Function: `normalize_markdown`

## Signature

```python
def normalize_markdown(markdown: str) -> str:
    ...
```

## Responsibility

Perform light deterministic cleanup after `markdownify`.

It should:

- strip trailing whitespace from each line
- collapse repeated blank lines
- trim leading/trailing blank space from the full document

It should not:

- remove factual text
- remove headings
- remove lists
- rewrite sentences
- summarize content
- remove links based on usefulness

---

# What This Sprint Must Not Do

Do not implement:

- `run_generate_markdown_pages()`
- Stage 04 harness
- JSONL artifact writing
- `generated_wiki/` folder writing
- fetching candidate URLs
- filename collision handling
- lead metadata writing
- market identity
- `farmles_wiki` import
- Git or GitHub
- SQL export
- LLM extraction

This sprint is only:

```text
html_to_markdown()
normalize_markdown()
unit tests
```

---

# TDD Requirements

Write unit tests first or alongside the implementation.

Create tests under:

```text
tests/unit/test_html_to_markdown.py
```

Use generated HTML from `tests/helpers/html_factory.py` when possible.

Do not use real websites.

Do not use network calls.

The unit tests should invoke `html_to_markdown()`, which internally invokes `markdownify`.

The tests should not call real network resources or depend on external websites.

---

# Required Unit Tests

## Test 1: preserves heading text

Given HTML:

```html
<h1>Apex Farmers Market</h1>
```

Expected markdown contains:

```md
# Apex Farmers Market
```

or equivalent ATX-style heading.

Prefer ATX heading style if configuring `markdownify`.

---

## Test 2: preserves factual paragraph text

Given HTML:

```html
<p>Hours: Saturdays 8 AM to 12 PM</p>
<p>Location: 123 Main Street, Apex, NC</p>
```

Expected markdown contains:

```text
Hours: Saturdays 8 AM to 12 PM
Location: 123 Main Street, Apex, NC
```

The converter must not rewrite or remove these facts.

---

## Test 3: preserves list content

Given HTML:

```html
<ul>
  <li>Smith Farm - vegetables and eggs</li>
  <li>Blue Ridge Bakery - bread and pastries</li>
</ul>
```

Expected markdown contains both:

```text
Smith Farm - vegetables and eggs
Blue Ridge Bakery - bread and pastries
```

The exact bullet character may depend on the library, but the factual text must remain.

---

## Test 4: preserves link text

Given HTML:

```html
<a href="https://example.org/vendors">Vendors</a>
```

Expected markdown contains:

```text
Vendors
```

If the markdown converter preserves the link URL, that is fine.

Example acceptable output:

```md
[Vendors](https://example.org/vendors)
```

---

## Test 5: appends source URL footer

Given:

```python
source_url = "https://example.org/vendors"
```

Expected markdown contains:

```md
Source: https://example.org/vendors
```

---

## Test 6: removes trailing whitespace

Given markdown or HTML that produces lines with trailing spaces, after conversion:

```python
for line in markdown.splitlines():
    assert line == line.rstrip()
```

---

## Test 7: collapses excessive blank lines

Given HTML with excessive spacing, the final markdown should not contain three or more consecutive blank lines.

A simple assertion is acceptable:

```python
assert "\n\n\n" not in markdown
```

---

## Test 8: does not remove factual content during cleanup

Given HTML containing multiple facts:

```html
<h1>Apex Farmers Market</h1>
<p>Hours: Saturdays 8 AM to 12 PM</p>
<p>Season: April through October</p>
<p>Location: 123 Main Street, Apex, NC</p>
```

Expected markdown still contains:

```text
Apex Farmers Market
Hours: Saturdays 8 AM to 12 PM
Season: April through October
Location: 123 Main Street, Apex, NC
```

---

## Test 9: normalize_markdown strips trailing whitespace independently

Call `normalize_markdown()` directly with a string that has trailing spaces:

```python
result = normalize_markdown("# Title   \n\nSome text   ")
for line in result.splitlines():
    assert line == line.rstrip()
```

---

## Test 10: normalize_markdown collapses consecutive blank lines independently

Call `normalize_markdown()` directly:

```python
result = normalize_markdown("line one\n\n\n\nline two")
assert "\n\n\n" not in result
assert "line one" in result
assert "line two" in result
```

---

## Test 11: normalize_markdown returns empty string for blank input

```python
assert normalize_markdown("") == ""
assert normalize_markdown("   \n\n   ") == ""
```

---

## Test 12: compute_content_hash returns sha256-prefixed string

```python
result = compute_content_hash("hello")
assert result.startswith("sha256:")
assert len(result) == len("sha256:") + 64
```

---

## Test 13: compute_content_hash is deterministic

Same input always produces the same hash:

```python
assert compute_content_hash("hello") == compute_content_hash("hello")
```

---

## Test 14: compute_content_hash differs for different inputs

```python
assert compute_content_hash("hello") != compute_content_hash("world")
```

---

## Dirty HTML / Edge Case Tests

The converter should be tolerant of imperfect HTML. These tests are not meant to make the converter a full sanitizer. They only prove that `markdownify` plus our cleanup does not crash and preserves obvious factual text.

Required dirty HTML tests:

### Test 15: malformed/unclosed HTML does not crash

```python
html = "<h1>Apex Market<p>Hours: Saturdays 8 AM"
result = html_to_markdown(html, "https://example.org/")
assert "Apex Market" in result
assert "Hours: Saturdays 8 AM" in result
```

### Test 16: empty HTML does not crash and still appends source footer

```python
result = html_to_markdown("", "https://example.org/")
assert "Source: https://example.org/" in result
```

### Test 17: script/style-only HTML does not crash

```python
html = "<style>body { color: red; }</style><script>alert('hi');</script>"
result = html_to_markdown(html, "https://example.org/")
assert "Source: https://example.org/" in result
```

### Test 18: excessive whitespace is normalized

```python
html = "<p>Some   text   with   extra   spaces</p>"
result = html_to_markdown(html, "https://example.org/")
assert "\n\n\n" not in result
```

### Test 19: empty `source_url` raises `ValueError`

```python
with pytest.raises(ValueError):
    html_to_markdown("<p>text</p>", "")
```

---

# Suggested Implementation Shape

```python
import hashlib
from markdownify import markdownify as md


def normalize_markdown(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]

    cleaned_lines: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = not line.strip()

        if is_blank and previous_blank:
            continue

        cleaned_lines.append(line)
        previous_blank = is_blank

    return "\n".join(cleaned_lines).strip()


def html_to_markdown(html: str, source_url: str) -> str:
    markdown = md(html, heading_style="ATX")
    markdown = normalize_markdown(markdown)

    return f"{markdown}\n\n---\n\nSource: {source_url}\n"


def compute_content_hash(markdown_text: str) -> str:
    digest = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
```

The implementer may adjust this if needed, but the tests above must pass.

---

# Acceptance Criteria

Sprint 7 is complete when:

1. `html_to_markdown()` is implemented in `farmles_harvester/stages/generate_markdown_pages.py`.
2. `normalize_markdown()` is implemented in the same file.
3. `compute_content_hash()` is implemented in the same file.
4. Unit tests exist for heading preservation.
5. Unit tests exist for factual paragraph preservation.
6. Unit tests exist for list preservation.
7. Unit tests exist for link text preservation.
8. Unit tests exist for source URL footer.
9. Unit tests exist for trailing whitespace cleanup.
10. Unit tests exist for blank-line cleanup.
11. Unit tests confirm factual content is not removed.
12. Unit tests for `normalize_markdown()` called independently (empty, whitespace-only, consecutive blank lines).
13. Unit tests for `compute_content_hash()` (format, determinism, different inputs differ).
14. Dirty HTML / edge case tests: malformed HTML, empty HTML, script/style-only HTML, excessive whitespace, empty `source_url`.
15. Tests do not use real network calls.
16. No Stage 04 harness is implemented.
17. No JSONL artifacts are written.
18. All tests pass with `pytest`.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Functions implemented.
3. Unit tests added.
4. Test command used.
5. Test result.
6. Any assumptions or deferred work.
