# Sprint 3 Prompt: Pipeline Record Contracts

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 3 only**.

Sprint 0 verified tooling.  
Sprint 1 implemented pure logic functions and unit tests.  
Sprint 2 implemented the Stage 00 harness for `normalize_source_leads`.

Sprint 3 should now define lightweight record contracts for pipeline JSONL records.

Do not implement Stage 01 yet.  
Do not implement the full orchestrator yet.  
Do not add real network crawling.  
Do not add GitHub or SQL functionality.

---

# Goal

Create shared, lightweight record contract helpers so pipeline stages can validate the minimum required fields in their input and output records.

The goal is to avoid two problems:

```text
1. Kitchen-sink records that carry every old field forever.
2. Rigid dataclasses that force us to guess the final schema too early.
```

Use flexible dicts for JSONL records, but enforce required fields.

Mental model:

```text
pipeline records = flexible dicts
record contracts = minimum required fields + validation helpers
```

---

# Why This Sprint Exists

The fields in pipeline JSONL records will evolve over time.

For v1, do not create rigid dataclasses for every pipeline record.

Instead, define the minimum required fields for each stage artifact and allow extra fields.

Example:

```python
record = {
    "run_id": "test-run",
    "source_lead_id": "lead_1",
    "normalized_url": "https://apexfarmersmarket.com/",
    "extra_debug_field": "allowed"
}
```

This should pass if the required fields are present.

---

# Required Files / Modules

Create:

```text
farmles_harvester/
  models/
    __init__.py
    record_contracts.py
```

Add or update tests:

```text
tests/
  unit/
    test_record_contracts.py

  harness/
    test_normalize_source_leads_stage.py
```

The Stage 00 harness tests should be updated to check that output records satisfy the Stage 00 record contract.

---

# Required Contract Definitions

In:

```text
farmles_harvester/models/record_contracts.py
```

Define required-field sets for each pipeline artifact.

## Stage 00 Output: `NORMALIZED_SOURCE_LEAD_REQUIRED`

This contract applies to:

```text
00_normalized_source_leads.jsonl
```

Required fields:

```python
NORMALIZED_SOURCE_LEAD_REQUIRED = {
    "run_id",
    "source_lead_id",
    "input_url",
    "normalized_url",
    "input_line",
    "normalized_at",
}
```

Optional fields may include:

```text
normalization_notes
```

Do not require optional fields yet.

---

## Stage 01 Output: `VALIDATED_SOURCE_REQUIRED`

This contract will apply to:

```text
01_validated_sources.jsonl
```

Required fields:

```python
VALIDATED_SOURCE_REQUIRED = {
    "run_id",
    "source_lead_id",
    "normalized_url",
    "final_url",
    "validation_status",
    "validated_at",
}
```

Optional fields may include:

```text
input_url
domain
http_status
content_type
redirected
redirect_chain
failure_reason
```

Do not implement Stage 01 in this sprint. Only define the contract.

---

## Stage 02 Output: `DISCOVERED_LINK_REQUIRED`

This contract will apply to:

```text
02_discovered_links.jsonl
```

Required fields:

```python
DISCOVERED_LINK_REQUIRED = {
    "run_id",
    "source_lead_id",
    "source_url",
    "discovered_url",
    "link_text",
    "is_internal",
    "follow_allowed",
}
```

Optional fields may include:

```text
raw_href
source_domain
discovered_domain
depth
discovery_method
discovered_at
```

Do not implement Stage 02 in this sprint. Only define the contract.

---

## Stage 03 Output: `CANDIDATE_URL_REQUIRED`

This contract will apply to:

```text
03_candidate_urls.jsonl
```

Required fields:

```python
CANDIDATE_URL_REQUIRED = {
    "run_id",
    "source_lead_id",
    "source_url",
    "candidate_url",
    "candidate_type",
    "candidate_score",
    "candidate_status",
}
```

Optional fields may include:

```text
link_text
candidate_strength
score_reasons
scored_at
```

Do not implement Stage 03 harness in this sprint. Only define the contract.

---

## Stage 04 Output: `MARKDOWN_PAGE_REQUIRED`

This contract will apply to:

```text
04_markdown_pages.jsonl
```

Required fields:

```python
MARKDOWN_PAGE_REQUIRED = {
    "run_id",
    "source_lead_id",
    "candidate_url",
    "candidate_type",
    "fetch_status",
    "markdown_path",
    "markdown_filename",
    "generated_at",
}
```

Optional fields may include:

```text
candidate_score
http_status
content_type
content_hash
```

Do not implement Stage 04 harness in this sprint. Only define the contract.

---

# Required Helper Functions

Implement these helpers in:

```text
farmles_harvester/models/record_contracts.py
```

## `missing_fields`

```python
def missing_fields(record: dict, required_fields: set[str]) -> set[str]:
    ...
```

Returns the required fields missing from the record.

Example:

```python
missing_fields({"run_id": "r1"}, {"run_id", "source_lead_id"})
```

Expected:

```python
{"source_lead_id"}
```

---

## `has_required_fields`

```python
def has_required_fields(record: dict, required_fields: set[str]) -> bool:
    ...
```

Returns `True` if all required fields are present.

Returns `False` otherwise.

Extra fields should be allowed.

---

## `require_fields`

```python
def require_fields(record: dict, required_fields: set[str]) -> None:
    ...
```

Raises a clear `ValueError` if any required field is missing.

Error message should include the missing field names.

Example error message:

```text
Missing required fields: ['source_lead_id']
```

Extra fields should not cause an error.

---

# Testing Requirements

Create tests in:

```text
tests/unit/test_record_contracts.py
```

## Test 1: `missing_fields` returns empty set when all required fields exist

Given:

```python
record = {"run_id": "r1", "source_lead_id": "lead_1"}
required = {"run_id", "source_lead_id"}
```

Expected:

```python
set()
```

---

## Test 2: `missing_fields` returns missing field names

Given:

```python
record = {"run_id": "r1"}
required = {"run_id", "source_lead_id"}
```

Expected:

```python
{"source_lead_id"}
```

---

## Test 3: `has_required_fields` returns True when complete

Given a complete record, expected:

```python
True
```

---

## Test 4: `has_required_fields` returns False when incomplete

Given a record missing one required field, expected:

```python
False
```

---

## Test 5: `require_fields` passes when all required fields exist

Given a complete record, it should not raise.

---

## Test 6: `require_fields` raises clear ValueError when fields are missing

Given an incomplete record, it should raise `ValueError`.

The error message should include the missing field name.

---

## Test 7: extra fields are allowed

Given:

```python
record = {
    "run_id": "r1",
    "source_lead_id": "lead_1",
    "extra_debug_field": "allowed"
}
required = {"run_id", "source_lead_id"}
```

Expected:

```text
passes validation
```

This is important. The record contract checks minimum required fields only.

---

## Test 8: required contract constants exist

Assert that these constants exist and are sets:

```text
NORMALIZED_SOURCE_LEAD_REQUIRED
VALIDATED_SOURCE_REQUIRED
DISCOVERED_LINK_REQUIRED
CANDIDATE_URL_REQUIRED
MARKDOWN_PAGE_REQUIRED
```

---

# Stage 00 Harness Test Update

Update the existing Stage 00 harness tests in:

```text
tests/harness/test_normalize_source_leads_stage.py
```

Add a test that reads records from:

```text
00_normalized_source_leads.jsonl
```

and verifies every output record satisfies:

```python
NORMALIZED_SOURCE_LEAD_REQUIRED
```

Example:

```python
for record in records:
    require_fields(record, NORMALIZED_SOURCE_LEAD_REQUIRED)
```

This connects the new record contract helpers to the first implemented stage.

---

# Important Design Rules

## Use dicts for pipeline JSONL records

Do not convert every pipeline record into a dataclass yet.

Reason:

```text
The JSONL schemas are still evolving.
Dicts are more flexible.
Required-field checks provide enough guardrail for v1.
```

## Use dataclasses only for stable code objects

Dataclasses are still appropriate for stable internal objects like:

```text
StagePaths
StageResult
NormalizedUrlResult
CandidateScore
FakeResponse
```

But for pipeline artifact records, use dicts plus contract validation.

## Allow extra fields

Record contracts should check minimum required fields only.

Extra fields must be allowed.

This avoids breaking the pipeline every time a stage adds useful metadata.

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

Sprint 3 is only:

```text
record contract constants
required-field helper functions
unit tests
Stage 00 harness test update
```

---

# Acceptance Criteria

Sprint 3 is complete when:

1. `farmles_harvester/models/__init__.py` exists.
2. `farmles_harvester/models/record_contracts.py` exists.
3. Required-field sets are defined for Stage 00 through Stage 04 artifacts.
4. `missing_fields()` is implemented.
5. `has_required_fields()` is implemented.
6. `require_fields()` is implemented.
7. Unit tests cover passing records, missing fields, extra fields, and contract constants.
8. Existing Stage 00 harness tests verify output records satisfy `NORMALIZED_SOURCE_LEAD_REQUIRED`.
9. All tests pass with `pytest`.
10. No new pipeline stage is implemented.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. Contract constants added.
3. Helper functions implemented.
4. Tests added or updated.
5. Test command used.
6. Test result.
7. Any assumptions or deferred work.
