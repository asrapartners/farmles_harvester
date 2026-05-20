# Sprint 2 Prompt: Stage 00 Harness for `normalize_source_leads`

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 2 only**.

Sprint 0 verified tooling.  
Sprint 1 implemented pure logic functions and unit tests.  
Sprint 2 should now build the first real pipeline stage harness for:

```text
00_normalize_source_leads
```

Do not implement the full orchestrator yet.  
Do not implement network stages yet.  
Do not implement later pipeline stages yet.

---

# Goal

Implement the Stage 00 harness that reads `seed_urls.txt` and writes the standard pipeline artifacts:

```text
00_normalized_source_leads.jsonl
00_normalized_source_leads_summary.json
00_normalized_source_leads_errors.jsonl
```

It must also return a JSON-serializable `StageResult`.

This sprint proves the stage harness pattern:

```text
input file
   ↓
stage harness
   ↓
output artifact
summary artifact
errors artifact
StageResult
```

---

# Pipeline Context

Current planned pipeline:

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

Sprint 2 only implements the harness for the first stage:

```text
00_normalize_source_leads
```

---

# Stage Purpose

`normalize_source_leads` converts a human-provided seed URL file into clean, unique, machine-readable source lead records.

Mental model:

```text
normalize = clean + standardize, not verify
```

This stage must not fetch URLs or check whether websites work.

---

# Required Files / Modules

Implement or update the following:

```text
farmles_harvester/
  pipeline/
    stage_paths.py
    stage_result.py
    jsonl.py

  stages/
    normalize_source_leads.py

tests/
  harness/
    test_normalize_source_leads_stage.py
```

If these files already exist from prior work, extend them without breaking existing tests.

---

# Required Pipeline Primitives

## 1. `StagePaths`

Suggested location:

```text
farmles_harvester/pipeline/stage_paths.py
```

Purpose:

`StagePaths` tells a stage where to write its output files.

It should contain absolute paths for code to write files.

Suggested dataclass:

```python
@dataclass
class StagePaths:
    output_path: Path
    summary_path: Path
    errors_path: Path

    @classmethod
    def for_stage(
        cls,
        run_dir: Path,
        stage_number: str,
        artifact_name: str,
    ) -> "StagePaths":
        ...
```

Example:

```python
StagePaths.for_stage(
    run_dir=Path("/tmp/run"),
    stage_number="00",
    artifact_name="normalized_source_leads",
)
```

Should produce:

```text
/tmp/run/00_normalized_source_leads.jsonl
/tmp/run/00_normalized_source_leads_summary.json
/tmp/run/00_normalized_source_leads_errors.jsonl
```

Rules:

- `StagePaths` should store absolute paths.
- The stage should not hardcode filenames.
- The orchestrator or test creates `StagePaths` and passes it to the stage harness.

---

## 2. `StageResult`

Suggested location:

```text
farmles_harvester/pipeline/stage_result.py
```

Purpose:

`StageResult` is the serializable receipt returned by a stage.

Suggested dataclass:

```python
@dataclass
class StageResult:
    stage_id: str
    stage_number: str
    stage_name: str
    status: str
    consumed_artifacts: list[str]
    produced_artifacts: list[str]
    summary_artifact: str | None
    error_artifact: str | None
    counts: dict[str, int]
    started_at: str
    completed_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ...
```

Allowed status values for this sprint:

```text
completed
failed
```

The `StageResult` should use artifact filenames, not full absolute paths.

Example produced artifacts:

```text
00_normalized_source_leads.jsonl
```

not:

```text
/tmp/run/00_normalized_source_leads.jsonl
```

---

## 3. JSONL Helpers

Suggested location:

```text
farmles_harvester/pipeline/jsonl.py
```

Implement small helpers:

```python
write_jsonl(path: Path, records: Iterable[dict]) -> None
read_jsonl(path: Path) -> list[dict]
```

Rules:

- Each record is one JSON object per line.
- Use UTF-8.
- Do not write one giant JSON array.
- Skip blank lines when reading.

---

# Stage Harness

Implement the stage harness in:

```text
farmles_harvester/stages/normalize_source_leads.py
```

Required function:

```python
run_normalize_source_leads(
    seed_file: Path,
    stage_paths: StagePaths,
    run_id: str,
    config: dict | None = None,
) -> StageResult
```

## Responsibilities

The harness must:

1. Read `seed_file`.
2. Use the Sprint 1 parsing/normalization logic.
3. Write unique normalized source lead records to:

```text
00_normalized_source_leads.jsonl
```

4. Write summary JSON to:

```text
00_normalized_source_leads_summary.json
```

5. Write error records to:

```text
00_normalized_source_leads_errors.jsonl
```

6. Return a JSON-serializable `StageResult`.

---

# Input

Input file:

```text
seed_urls.txt
```

Example:

```text
# NC market source leads

apexfarmersmarket.com
https://apexfarmersmarket.com/
https://www.localharvest.org/farmers-markets?utm_source=test
bad url here
```

Rules:

- Blank lines are skipped.
- Lines starting with `#` are skipped.
- Duplicate normalized URLs are not emitted twice.
- Invalid/malformed URLs are written to the errors artifact.

---

# Output Artifact Contract

Write:

```text
00_normalized_source_leads.jsonl
```

Each line must be one JSON object.

Required fields:

```text
run_id
source_lead_id
input_url
normalized_url
input_line
normalization_notes
normalized_at
```

Example:

```json
{
  "run_id": "test-run",
  "source_lead_id": "lead_1",
  "input_url": "apexfarmersmarket.com",
  "normalized_url": "https://apexfarmersmarket.com/",
  "input_line": 3,
  "normalization_notes": ["added_https_scheme", "added_trailing_slash"],
  "normalized_at": "2026-05-17T13:24:00Z"
}
```

Important:

- Do not include duplicate normalized URLs in the output.
- Do not include invalid URLs in the output.
- `source_lead_id` is run-local and should be assigned only to emitted unique valid records.

---

# Summary Artifact Contract

Write:

```text
00_normalized_source_leads_summary.json
```

Required fields:

```text
stage_name
stage_number
input_lines
comment_lines_skipped
blank_lines_skipped
output_records
duplicate_records_skipped
invalid_records
error_records
started_at
completed_at
```

Example:

```json
{
  "stage_name": "normalize_source_leads",
  "stage_number": "00",
  "input_lines": 5,
  "comment_lines_skipped": 1,
  "blank_lines_skipped": 1,
  "output_records": 2,
  "duplicate_records_skipped": 1,
  "invalid_records": 1,
  "error_records": 1,
  "started_at": "2026-05-17T13:24:00Z",
  "completed_at": "2026-05-17T13:24:01Z"
}
```

---

# Error Artifact Contract

Write:

```text
00_normalized_source_leads_errors.jsonl
```

Each line must be one JSON object.

Use this for malformed or invalid input lines.

Required fields:

```text
run_id
stage_name
input_line
input_url
error_type
message
retryable
created_at
```

Example:

```json
{
  "run_id": "test-run",
  "stage_name": "normalize_source_leads",
  "input_line": 5,
  "input_url": "bad url here",
  "error_type": "malformed_url",
  "message": "Could not normalize input as a valid HTTP/HTTPS URL",
  "retryable": false,
  "created_at": "2026-05-17T13:24:00Z"
}
```

Duplicates are not errors. They are counted in the summary only.

---

# StageResult Contract

The harness must return `StageResult`.

Example:

```json
{
  "stage_id": "00_normalize_source_leads",
  "stage_number": "00",
  "stage_name": "normalize_source_leads",
  "status": "completed",
  "consumed_artifacts": ["seed_urls.txt"],
  "produced_artifacts": ["00_normalized_source_leads.jsonl"],
  "summary_artifact": "00_normalized_source_leads_summary.json",
  "error_artifact": "00_normalized_source_leads_errors.jsonl",
  "counts": {
    "input_lines": 5,
    "comment_lines_skipped": 1,
    "blank_lines_skipped": 1,
    "output_records": 2,
    "duplicate_records_skipped": 1,
    "invalid_records": 1,
    "error_records": 1
  },
  "started_at": "2026-05-17T13:24:00Z",
  "completed_at": "2026-05-17T13:24:01Z"
}
```

The returned object must be convertible to a plain dict and JSON-serializable.

---

# Tests Required

Create harness tests in:

```text
tests/harness/test_normalize_source_leads_stage.py
```

## Test 1: writes standard artifacts

Given a small `seed_urls.txt`, running `run_normalize_source_leads()` should create:

```text
00_normalized_source_leads.jsonl
00_normalized_source_leads_summary.json
00_normalized_source_leads_errors.jsonl
```

## Test 2: output JSONL contains valid unique records

Input:

```text
apexfarmersmarket.com
https://apexfarmersmarket.com/
https://www.localharvest.org/farmers-markets?utm_source=test
```

Expected:

- duplicate Apex URL is emitted only once
- LocalHarvest URL is emitted once
- output has 2 records

## Test 3: comments and blanks are skipped

Input:

```text
# comment

apexfarmersmarket.com
```

Expected:

- one output record
- summary counts one comment line
- summary counts one blank line

## Test 4: invalid input writes error

Input:

```text
bad url here
```

Expected:

- zero output records
- one error record
- summary `invalid_records = 1`
- summary `error_records = 1`

## Test 5: StageResult is serializable

After running the stage:

- call `result.to_dict()`
- serialize with `json.dumps()`
- assert it succeeds

## Test 6: artifact paths use StagePaths

Verify the stage writes to the exact files provided by `StagePaths`.

The stage should not write to hardcoded locations.

---

# Boundaries

Do not implement:

- full orchestrator
- manifest.json updates
- validate_urls stage
- network fetching
- discover_links stage
- score_candidate_urls harness
- generated_wiki
- Git/GitHub
- SQL export
- LLM extraction

This sprint is only:

```text
StagePaths + StageResult + JSONL helpers + Stage 00 harness + harness tests
```

---

# Definition of Done

Sprint 2 is complete when:

1. `StagePaths` exists and creates correct absolute output paths.
2. `StageResult` exists and is JSON-serializable.
3. JSONL helpers exist and are tested indirectly or directly.
4. `run_normalize_source_leads()` is implemented.
5. Stage writes output JSONL, summary JSON, and errors JSONL.
6. Stage returns a valid `StageResult`.
7. Harness tests pass.
8. No later pipeline stages are implemented.
9. No real network access is used.
10. No manifest/orchestrator logic is implemented.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Harness implemented.
3. Tests added.
4. Test command used.
5. Test result.
6. Any assumptions or deferred work.
