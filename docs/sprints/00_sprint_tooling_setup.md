# Sprint 0 Prompt: farmles_harvester Tooling Setup

You are the implementer agent for `farmles_harvester`.

Your task is **Sprint 0 only**.

Do not implement the full crawler pipeline yet.  
Do not build the orchestrator yet.  
Do not implement all stages yet.

Sprint 0 is only about setting up the project structure, installing/configuring basic tools, and proving that the core HTML tooling works on a tiny sample page.

---

# Goal

Prove that the local development environment can:

1. Run Python tests.
2. Parse a small HTML file.
3. Extract links from HTML.
4. Convert HTML to markdown.
5. Use a fake fetcher so tests do not require internet access.

This sprint is a tooling and confidence sprint.

---

# Repository Name

```text
farmles_harvester
```

Use this project layout:

```text
farmles_harvester/
  README.md
  pyproject.toml
  .gitignore

  farmles_harvester/
    __init__.py

  tests/
    helpers/
      __init__.py
      html_factory.py
      fake_fetcher.py

    unit/
      test_html_tools.py

  samples/
    mock_sites/
      simple_market/
        home.html

  runs/
    .gitkeep
```

Do not use a `src/` folder for Sprint 0.

---

# Python / Tooling Requirements

Use Python 3.11 or later.

Set up `pyproject.toml` with:

- project metadata
- pytest configuration
- dependencies needed for Sprint 0

Recommended dependencies:

```text
pytest
beautifulsoup4
markdownify
```

Optional but okay:

```text
ruff
```

Do not add heavy crawler dependencies yet unless needed.

Do not add `crawl4ai` in Sprint 0 unless you have a strong reason. Start simple.

---

# Required Files

## 1. `.gitignore`

Include:

```gitignore
# Python
__pycache__/
*.py[cod]
.pytest_cache/
.venv/

# Generated runs
runs/*
!runs/.gitkeep

# OS/editor
.DS_Store
.vscode/
.idea/
```

---

## 2. `README.md`

Create a short README explaining:

- this repo is the crawler/markdown generator
- Sprint 0 only verifies tooling
- how to install dependencies
- how to run tests

Example commands:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Use Windows-compatible wording if appropriate, but do not overdo it.

---

## 3. `samples/mock_sites/simple_market/home.html`

Create a tiny sample HTML page.

It should include:

- page title
- heading
- internal links
- external link
- junk link

Example content should include links like:

```html
<a href="/vendors">Vendors</a>
<a href="/visit">Visit Us</a>
<a href="/events">Events</a>
<a href="/privacy-policy">Privacy Policy</a>
<a href="https://facebook.com/apexmarket">Facebook</a>
<a href="mailto:info@example.org">Email</a>
```

This file is a small local sample, not a realistic full website.

---

## 4. `tests/helpers/html_factory.py`

Create a helper function:

```python
def make_html_page(
    title: str = "Test Page",
    links: list[tuple[str, str]] | None = None,
    body: str = "",
) -> str:
    ...
```

It should return a small valid HTML string with the given links.

This helper is used by tests so we do not manually maintain many sample files.

---

## 5. `tests/helpers/fake_fetcher.py`

Create a fake fetcher for tests.

It should include:

```python
@dataclass
class FakeResponse:
    url: str
    status_code: int
    content_type: str
    text: str
```

and:

```python
class FakeFetcher:
    def __init__(self, pages: dict[str, FakeResponse]):
        ...

    def fetch(self, url: str) -> FakeResponse:
        ...
```

`FakeFetcher` should:

- record requested URLs
- return a registered fake response
- raise a clear error if the URL is not registered

No real network calls.

---

## 6. `tests/unit/test_html_tools.py`

Create unit tests proving the tooling works.

At minimum, tests should verify:

### Test 1: BeautifulSoup can extract links

Given generated HTML with:

```text
/vendors
/visit
https://facebook.com/apexmarket
mailto:info@example.org
```

Assert that the href values and link text can be extracted.

### Test 2: markdownify can convert HTML to markdown

Given simple HTML with heading and links, convert it to markdown and assert:

```text
heading text appears
Vendors appears
Visit Us appears
```

### Test 3: FakeFetcher returns expected response

Register:

```text
https://apex.example/
```

with fake HTML.

Assert:

```text
fetcher.fetch("https://apex.example/") returns the fake response
requested_urls records the URL
```

### Test 4: FakeFetcher fails clearly for unknown URL

Call:

```text
fetcher.fetch("https://unknown.example/")
```

Assert that it raises a clear exception.

### Test 5: sample HTML file exists and can be parsed

Read:

```text
samples/mock_sites/simple_market/home.html
```

Parse it with BeautifulSoup.

Assert that it contains expected links:

```text
/vendors
/visit
/events
/privacy-policy
```

---

# Important Boundaries

Do not implement:

- orchestrator
- StagePaths
- StageResult
- JSONL artifacts
- URL validation
- real network fetching
- link scoring
- markdown generation stage
- GitHub PR logic
- SQL export
- LLM extraction

Sprint 0 is only setup + tool verification.

---

# Acceptance Criteria

Sprint 0 is complete when:

1. Project structure exists.
2. `pyproject.toml` is valid.
3. `.gitignore` is configured.
4. Sample HTML file exists.
5. `html_factory.py` exists.
6. `fake_fetcher.py` exists.
7. `test_html_tools.py` exists.
8. `pytest` passes.
9. Tests do not require internet access.
10. No full pipeline logic is implemented.

---

# Output Expected From Agent

When finished, report:

1. Files created.
2. Dependencies added.
3. Test command used.
4. Test result.
5. Any issues or assumptions.

Keep the implementation small and boring.
