# Sprint 4 Prompt: Formalize Pipeline Primitives

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 4 only**.

Sprint 0 verified tooling.  
Sprint 1 implemented pure logic functions and unit tests.  
Sprint 2 implemented the Stage 00 harness for `normalize_source_leads`.  
Sprint 3 added lightweight record contracts for JSONL pipeline records.

Sprint 4 should now formalize the shared pipeline primitives that every stage harness will depend on.

Do not implement Stage 01 yet.  
Do not implement the full orchestrator yet.  
Do not add real network crawling.  
Do not add GitHub or SQL functionality.

---

# Goal

Formalize the common infrastructure objects used by all pipeline stages:

```text
StagePaths
StageResult
JSONL helpers
artifact filename conventions
```

The goal is to remove ambiguity before implementing more stage harnesses.

Mental model:

```text
StagePaths = planned file destinations for one stage
StageResult = receipt describing what one stage actually produced
JSONL helpers = consistent record reading/writing
```

---

# Why This Sprint Exists

All stages follow the same artifact pattern:

```text
{stage_number}_{artifact_name}.jsonl
{stage_number}_{artifact_name}_summary.json
{stage_number}_{artifact_name}_errors.jsonl
```

Example:

```text
00_normalized_source_leads.jsonl
00_normalized_source_leads_summary.json
00_normalized_source_leads_errors.jsonl

01_validated_sources.jsonl
01_validated_sources_summary.json
01_validated_sources_errors.jsonl
```

`StagePaths` should be the same shape for all stages.

`StageResult` should have the same outer structure for all stages, but stage-specific `counts` and `metadata`.

---

# Required Files / Modules

Update or create:

```text
farmles_harvester/
  pipeline/
    __init__.py
    stage_paths.py
    stage_result.py
    jsonl.py
```

Add or update tests:

```text
tests/
  unit/
    test_stage_paths.py
    test_stage_result.py
    test_jsonl.py
```

If these files already exist from Sprint 2, refactor them to match this spec without breaking Stage 00 harness tests.

---

# 1. StagePaths

## Location

```text
farmles_harvester/pipeline/stage_paths.py
```

## Purpose

`StagePaths` is a short-lived object created for one stage execution.

It tells the stage harness exactly where to write:

```text
output artifact
summary artifact
errors artifact
```

The object exists only while the stage runs. The files it points to remain on disk.

## Required Dataclass

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
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

## Rules

1. `StagePaths` should store absolute paths.
2. `run_dir` may be passed as relative or absolute, but the stored paths should be absolute.
3. The stage harness should not construct filenames manually.
4. The stage harness should write only to the paths it receives.
5. The exact filenames are derived from `stage_number` and `artifact_name`.

### TDD Guidance for StagePaths

`StagePaths.for_stage()` owns the artifact filename convention.

The orchestrator or test provides:

```text
run_dir
stage_number
artifact_name
```

## Filename Derivation
Stage harnesses must not derive or hardcode artifact filenames.

Harness tests should create StagePaths and assert that the stage writes to the provided paths.

Given:

```python
run_dir = Path("/tmp/run")
stage_number = "00"
artifact_name = "normalized_source_leads"
```

`StagePaths.for_stage()` should produce:

```text
/tmp/run/00_normalized_source_leads.jsonl
/tmp/run/00_normalized_source_leads_summary.json
/tmp/run/00_normalized_source_leads_errors.jsonl
```

Given:

```python
run_dir = Path("/tmp/run")
stage_number = "01"
artifact_name = "validated_sources"
```

It should produce:

```text
/tmp/run/01_validated_sources.jsonl
/tmp/run/01_validated_sources_summary.json
/tmp/run/01_validated_sources_errors.jsonl
```

---

# 2. StageResult

## Location

```text
farmles_harvester/pipeline/stage_result.py
```

## Purpose

`StageResult` is the serializable receipt returned by a stage harness.

It describes:

```text
which stage ran
whether it completed
which artifacts it consumed
which artifacts it produced
summary/error artifact names
stage-specific counts
stage-specific metadata
timestamps
```

The orchestrator will later write `StageResult` into `manifest.json`.

Stages must not update `manifest.json` directly.

## Required Dataclass

```python
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class StageResult:
    stage_id: str
    stage_number: str
    stage_name: str
    status: str

    consumed_artifacts: list[str] = field(default_factory=list)
    produced_artifacts: list[str] = field(default_factory=list)

    summary_artifact: str | None = None
    error_artifact: str | None = None

    counts: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ...
```

## Allowed Status Values

For v1:

```text
completed
failed
skipped
```

Implement this as a constant if useful:

```python
STAGE_STATUS_COMPLETED = "completed"
STAGE_STATUS_FAILED = "failed"
STAGE_STATUS_SKIPPED = "skipped"
```

Do not over-engineer enums unless already simple.

## Artifact Path Rule

`StageResult` should store run-relative artifact filenames, not absolute paths.

Good:

```json
{
  "produced_artifacts": ["00_normalized_source_leads.jsonl"],
  "summary_artifact": "00_normalized_source_leads_summary.json",
  "error_artifact": "00_normalized_source_leads_errors.jsonl"
}
```

Bad:

```json
{
  "produced_artifacts": ["/Users/me/project/runs/run1/00_normalized_source_leads.jsonl"]
}
```

Reason:

```text
StagePaths = absolute paths used by code
StageResult = portable artifact names used by manifest
```

## Counts Rule

`counts` is stage-specific.

Example Stage 00 counts:

```json
{
  "input_lines": 5,
  "output_records": 2,
  "duplicate_records_skipped": 1,
  "invalid_records": 1,
  "error_records": 1
}
```

Future Stage 01 counts may be different:

```json
{
  "input_records": 10,
  "valid_count": 7,
  "redirected_count": 1,
  "broken_count": 1,
  "timeout_count": 1
}
```

The `StageResult` structure is common, but `counts` content is stage-specific.

## Metadata Rule

`metadata` is optional and stage-specific.

Use it for extra details that do not belong in `counts`.

Example:

```json
{
  "skip_reason": "no_changes_detected"
}
```

Do not put full record data in `metadata`.

---

# 3. JSONL Helpers

## Location

```text
farmles_harvester/pipeline/jsonl.py
```

## Purpose

Provide consistent helper functions for reading and writing JSONL artifacts.

## Required Functions

```python
from pathlib import Path
from typing import Iterable, Any


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    ...


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    ...
```

## Rules

1. JSONL means one JSON object per line.
2. Do not write one giant JSON array.
3. Use UTF-8.
4. Reading should skip blank lines.
5. Writing should create parent directories if needed.
6. Output should be valid JSON per line.
7. Do not silently swallow invalid JSON on read; let the caller see the error.

---

# 4. Summary JSON Helper Optional

Optional but allowed:

```python
def write_json(path: Path, obj: dict[str, Any]) -> None:
    ...
```

If implemented, test it.

Do not overbuild a generic storage abstraction.

---

# Required Tests

## `tests/unit/test_stage_paths.py`

### Test 1: creates expected filenames

Given:

```python
run_dir = tmp_path / "run"
stage_number = "00"
artifact_name = "normalized_source_leads"
```

Expected filenames:

```text
00_normalized_source_leads.jsonl
00_normalized_source_leads_summary.json
00_normalized_source_leads_errors.jsonl
```

### Test 2: paths are absolute

Given:

```python
run_dir = Path("relative/run")  # relative, not absolute
stage_number = "00"
artifact_name = "normalized_source_leads"
```

`StagePaths.for_stage()` should store absolute paths.

Expected:

```text
paths.output_path.is_absolute() is True
paths.summary_path.is_absolute() is True
paths.errors_path.is_absolute() is True
```

### Test 3: different stage creates different filenames

Given:

```python
stage_number = "01"
artifact_name = "validated_sources"
```

Expected:

```text
01_validated_sources.jsonl
01_validated_sources_summary.json
01_validated_sources_errors.jsonl
```

---

## `tests/unit/test_stage_result.py`

### Test 1: StageResult converts to dict

Create a `StageResult`.

Call:

```python
result.to_dict()
```

Expected:

```text
returns plain dict
contains stage_id
contains stage_number
contains stage_name
contains status
contains counts
```

### Test 2: StageResult is JSON-serializable

Call:

```python
json.dumps(result.to_dict())
```

Expected:

```text
does not raise
```

### Test 3: artifact names are relative strings

Create a result with:

```python
produced_artifacts=["00_normalized_source_leads.jsonl"]
```

Expected:

```text
to_dict() keeps the relative filename
```

### Test 4: default lists/dicts are independent

Create two `StageResult` objects.

Mutate `counts` or `metadata` in one.

Expected:

```text
the other object is not affected
```

This verifies correct use of `default_factory`.

---

## `tests/unit/test_jsonl.py`

### Test 1: write and read JSONL round trip

Given:

```python
records = [
    {"id": 1, "name": "A"},
    {"id": 2, "name": "B"},
]
```

Write to JSONL and read back.

Expected:

```text
read records equal original records
```

### Test 2: read skips blank lines

Given a JSONL file with blank lines.

Expected:

```text
blank lines are ignored
valid records are returned
```

### Test 3: write creates parent directory

Given a nested output path whose parent does not exist.

Expected:

```text
write_jsonl creates parent directory and writes file
```

### Test 4: invalid JSON raises

Given a JSONL file with invalid JSON.

Expected:

```text
read_jsonl raises an exception
```

Do not hide malformed artifacts.

---

# Stage 00 Compatibility Requirement

After refactoring pipeline primitives, existing Sprint 2 Stage 00 harness tests must still pass.

If the Stage 00 harness currently has local versions of `StagePaths`, `StageResult`, or JSONL helpers, update it to use the shared versions from:

```text
farmles_harvester/pipeline/
```

Do not change Stage 00 business behavior in this sprint.

---

# Non-Responsibilities

Do not implement:

- Stage 01 validate_urls harness
- Stage 02 discover_links harness
- Stage 03 score_candidate_urls harness
- Stage 04 generate_markdown_pages harness
- orchestrator
- manifest updates
- real network calls
- generated_wiki output
- Git/GitHub
- SQL export
- LLM extraction

Sprint 4 is only:

```text
StagePaths
StageResult
JSONL helpers
unit tests
Stage 00 compatibility
```

---

# Acceptance Criteria

Sprint 4 is complete when:

1. `StagePaths` is implemented in `farmles_harvester/pipeline/stage_paths.py`.
2. `StagePaths.for_stage()` creates correct absolute paths.
3. `StageResult` is implemented in `farmles_harvester/pipeline/stage_result.py`.
4. `StageResult.to_dict()` returns a JSON-serializable dict.
5. JSONL helpers are implemented in `farmles_harvester/pipeline/jsonl.py`.
6. Unit tests exist for StagePaths.
7. Unit tests exist for StageResult.
8. Unit tests exist for JSONL helpers.
9. Existing Stage 00 harness tests still pass.
10. No new pipeline stage is implemented.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Pipeline primitive behavior implemented.
3. Unit tests added.
4. Compatibility changes made to Stage 00, if any.
5. Test command used.
6. Test result.
7. Any assumptions or deferred work.
