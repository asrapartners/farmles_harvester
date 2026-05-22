# Sprint 11 Prompt: Markdown Stability Hardening

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 11 only**.

This is a hardening sprint, not a new feature sprint.

Sprint 7 implemented the HTML-to-Markdown converter.  
Sprint 8 implemented the Stage 04 `generate_markdown_pages` harness.

Sprint 11 adds stability guarantees so repeated runs do not create noisy Git diffs in `farmles_wiki`.

---

# Goal

Ensure that repeated runs with the same HTML input produce identical markdown output.

This is important because generated markdown will later be imported into `farmles_wiki`.

If the website content has not changed, the regenerated `.md` files should be identical.

That means Git should show no diff.

Mental model:

```text
same HTML
same source URL
same candidate input
   ↓
same markdown files
   ↓
no unnecessary Git diff
```

---

# Problem This Sprint Solves

If generated markdown includes volatile values, every run can produce a diff even when the source website did not change.

Examples of volatile values:

```text
generated_at timestamp
run_id
local file path
random ID
current date/time
temporary directory
```

These values are allowed in run artifacts like:

```text
manifest.json
04_markdown_pages.jsonl
lead_metadata.json
```

But they should not appear inside the generated `.md` content.

---

# Scope

Add tests and small fixes for:

```text
html_to_markdown()
normalize_markdown()
run_generate_markdown_pages()
```

This sprint may update implementation only as needed to pass stability tests.

---

# Non-Goals

Do not implement:

- new crawler stages
- semantic HTML cleanup
- boilerplate removal
- link scoring changes
- market identity logic
- farmles_wiki import
- Git/GitHub automation
- SQL export
- LLM extraction

This sprint is only about markdown stability.

---

# Stability Requirements

## Requirement 1: `html_to_markdown()` is deterministic

Given the same HTML and same source URL:

```python
first = html_to_markdown(html, source_url)
second = html_to_markdown(html, source_url)
```

Expected:

```python
first == second
```

---

## Requirement 2: Markdown does not include volatile values

Generated markdown must not include:

```text
generated_at
Generated at
run_id
Run ID
/tmp/
temp/
timestamp-like generated metadata
```

Do not add timestamps or run metadata to `.md` content.

A source URL footer is allowed and required.

Allowed:

```md
---

Source: https://example.org/vendors
```

Not allowed:

```md
Generated at: 2026-05-21T10:30:00Z
Run ID: 2026-05-21_103000_test
```

---

## Requirement 3: `normalize_markdown()` is deterministic

Given the same markdown string:

```python
first = normalize_markdown(markdown)
second = normalize_markdown(markdown)
```

Expected:

```python
first == second
```

---

## Requirement 4: Stage 04 generated `.md` files are stable across repeated runs

Given:

```text
same 03_candidate_urls.jsonl
same fake fetcher responses
```

Running `run_generate_markdown_pages()` twice in two separate temporary run folders should produce identical `.md` file content.

Only compare `.md` files.

Do not require JSONL artifacts or metadata files to be identical, because those may contain timestamps.

---

# Required Unit Tests

Create or update:

```text
tests/unit/test_html_to_markdown.py
```

## Test 1: `html_to_markdown()` is deterministic

Given simple HTML:

```html
<h1>Apex Farmers Market</h1>
<p>Hours: Saturdays 8 AM to 12 PM</p>
```

Call `html_to_markdown()` twice with the same `source_url`.

Expected:

```python
first == second
```

---

## Test 2: markdown does not include volatile generated metadata

Given normal HTML and a source URL.

Expected markdown does not contain:

```text
generated_at
Generated at
run_id
Run ID
```

Also assert it does contain:

```text
Source: <source_url>
```

---

## Test 3: `normalize_markdown()` is deterministic

Given markdown with trailing spaces and repeated blank lines.

Call `normalize_markdown()` twice.

Expected:

```python
first == second
```

---

## Test 4: stable cleanup output

Given markdown with:

```text
trailing spaces
three or more blank lines
leading/trailing blank space
```

Expected:

```text
no trailing whitespace
no triple blank lines
same cleaned output every time
```

---

# Required Harness Tests

Create or update:

```text
tests/harness/test_generate_markdown_pages_stage.py
```

## Test 5: generated markdown files are stable across runs

Use the same input `03_candidate_urls.jsonl` and the same fake fetcher HTML.

Run Stage 04 twice using separate temp run folders.

Example:

```text
run1/
  generated_wiki/lead_1/vendors.md

run2/
  generated_wiki/lead_1/vendors.md
```

Expected:

```python
vendors_md_run1 == vendors_md_run2
```

This test should compare only `.md` file contents.

Do not compare:

```text
04_markdown_pages.jsonl
04_markdown_pages_summary.json
lead_metadata.json
manifest.json
```

Those files may contain timestamps and are not part of the GitHub wiki markdown diff.

---

## Test 6: repeated run does not create volatile markdown differences

Given HTML:

```html
<h1>Vendors</h1>
<ul>
  <li>Smith Farm - vegetables and eggs</li>
</ul>
```

Expected markdown from both runs contains:

```text
Vendors
Smith Farm - vegetables and eggs
Source: https://apex.example/vendors
```

and does not contain:

```text
generated_at
run_id
```

---

# Implementation Guidance

If the tests fail because markdown contains volatile values, remove those values from `.md` generation.

Keep volatile metadata in:

```text
04_markdown_pages.jsonl
lead_metadata.json
manifest.json
```

Do not place volatile metadata in `.md` content.

The `.md` file should contain only:

```text
converted page content
source URL footer
```

---

# Git Diff Rationale

This sprint supports the `farmles_wiki` Git workflow.

If regenerated markdown is unchanged, then after importing into `farmles_wiki`:

```bash
git status
```

should show no changes.

If source content changes, then Git should show a meaningful diff.

The goal is:

```text
real content changes → Git diff
no content changes → no Git diff
```

---

# Acceptance Criteria

Sprint 11 is complete when:

1. Unit test confirms `html_to_markdown()` is deterministic.
2. Unit test confirms `normalize_markdown()` is deterministic.
3. Unit test confirms markdown does not include volatile generated metadata.
4. Harness test confirms Stage 04 produces identical `.md` file contents across repeated runs with the same inputs.
5. Existing Sprint 7 and Sprint 8 tests still pass.
6. No new pipeline stage is added.
7. No Git/GitHub automation is added.
8. No semantic cleanup or LLM extraction is added.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Stability tests added.
3. Implementation changes made, if any.
4. Test command used.
5. Test result.
6. Any assumptions or deferred work.
