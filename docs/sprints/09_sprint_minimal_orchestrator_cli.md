# Sprint 9 Prompt: Minimal Orchestrator and CLI

You are the implementer/tester agent for `farmles_harvester`.

Your task is **Sprint 9 only**.

Previous sprints implemented:

```text
Sprint 0 = tooling setup
Sprint 1 = pure logic + unit tests
Sprint 2 = Stage 00 normalize_source_leads harness
Sprint 3 = record contracts
Sprint 4 = pipeline primitives
Sprint 5 = Stage 01 validate_urls harness
Sprint 6 = Stage 02 discover_links + Stage 03 score_candidate_urls harnesses
Sprint 7 = HTML-to-markdown converter logic
Sprint 8 = Stage 04 generate_markdown_pages harness
```

Sprint 9 should now wire the existing stages together with a minimal local orchestrator and CLI.

Do not implement `farmles_wiki` import logic.  
Do not implement Git/GitHub Pull Request logic.  
Do not implement SQL export.  
Do not use real internet in automated tests.

---

# Goal

Implement the first end-to-end local pipeline runner.

The orchestrator should:

1. Accept a seed file and tag.
2. Create a run folder.
3. Copy the seed file into the run folder.
4. Create `manifest.json`.
5. Run Stage 00 through Stage 04 in order.
6. Record each `StageResult` in the manifest.
7. Produce `generated_wiki/`.
8. Stop on failed stage.

High-level flow:

```text
seed_urls.txt
   ↓
farmles_harvester CLI
   ↓
orchestrator
   ↓
runs/{timestamp}_{tag}/
   ↓
00_normalized_source_leads.jsonl
01_validated_sources.jsonl
02_discovered_links.jsonl
03_candidate_urls.jsonl
04_markdown_pages.jsonl
generated_wiki/
manifest.json
```

---

# Required Files / Modules

Implement or update:

```text
farmles_harvester/
  cli.py

  orchestrator/
    __init__.py
    run_pipeline.py
    manifest.py
```

Use existing modules:

```text
farmles_harvester/pipeline/stage_paths.py
farmles_harvester/pipeline/stage_result.py
farmles_harvester/pipeline/jsonl.py

farmles_harvester/stages/normalize_source_leads.py
farmles_harvester/stages/validate_urls.py
farmles_harvester/stages/discover_links.py
farmles_harvester/stages/score_candidate_urls.py
farmles_harvester/stages/generate_markdown_pages.py
```

Define the pipeline failure exception in:

```text
farmles_harvester/orchestrator/exceptions.py
```

```python
class PipelineError(Exception):
    def __init__(self, message: str, stage_id: str, run_dir: Path):
        super().__init__(message)
        self.stage_id = stage_id
        self.run_dir = run_dir
```

`run_pipeline()` raises `PipelineError` when a stage returns `status = "failed"`. The CLI catches it to print a structured failure message and exit with a non-zero status.

Add tests:

```text
tests/
  harness/
    test_orchestrator.py

  unit/
    test_manifest.py
```

Add the CLI entry point to `pyproject.toml`:

```toml
[project.scripts]
farmles_harvester = "farmles_harvester.cli:main"
```

After updating `pyproject.toml`, re-run `pip install -e .` (or equivalent) so the `farmles_harvester` command is available in the virtualenv.

---

# CLI Contract

The user should be able to run:

```bash
farmles_harvester   --seed-file ./samples/seed_urls.txt   --tag smoke-test
```

Optional for tests or future use:

```bash
farmles_harvester   --seed-file ./samples/seed_urls.txt   --tag smoke-test   --runs-dir ./runs
```

## Required CLI Arguments

```text
--seed-file
Path to user-provided seed URL file.

--tag
Human-readable label for the run.
```

## Optional CLI Arguments

```text
--runs-dir
Directory where run folders are created.
Default: runs/ (relative to the current working directory at time of invocation)
```

Do not add `--wiki-repo-path` in this sprint.  
The harvester no longer owns wiki import.

---

# Run Folder Naming

The orchestrator should create:

```text
runs/{timestamp}_{tag}/
```

Example:

```text
runs/2026-05-17_132400_smoke-test/
```

Rules:

- Timestamp should be sortable.
- Tag should be filesystem-safe.
- If the same folder already exists, fail clearly or add a deterministic suffix.
- Do not overwrite an existing run folder.

Recommended timestamp format:

```text
YYYY-MM-DD_HHMMSS
```

---

# Seed File Snapshot

The orchestrator must copy the provided seed file into the run folder as:

```text
seed_urls.txt
```

The pipeline should use the copied file, not the original external path.

Reason:

```text
Each run folder should contain the exact input seed file used for that run.
```

---

# Manifest

Create:

```text
manifest.json
```

The manifest is the run ledger.

## Initial Manifest

Before stages run, create an initial manifest like:

```json
{
  "run_id": "2026-05-17_132400_smoke-test",
  "created_at": "2026-05-17T13:24:00Z",
  "tag": "smoke-test",
  "seed_file_snapshot": "seed_urls.txt",
  "stages": {},
  "execution_log": []
}
```

## Manifest Updates

After each stage completes, the orchestrator should:

1. Convert `StageResult` to dict.
2. Store it under `stages[stage_id]`.
3. Append a small entry to `execution_log`.

The `sequence` field is 1-indexed and derived from `len(manifest["execution_log"]) + 1` before appending.

Example after Stage 00 completes:

```json
{
  "sequence": 1,
  "stage_id": "00_normalize_source_leads",
  "status": "completed",
  "started_at": "2026-05-17T13:24:00Z",
  "completed_at": "2026-05-17T13:24:01Z"
}
```

## Important Rule

Stages must not update `manifest.json`.

Only the orchestrator updates the manifest.

---

# Manifest Helper

Implement in:

```text
farmles_harvester/orchestrator/manifest.py
```

Suggested functions:

```python
create_initial_manifest(
    run_id: str,
    tag: str,
    seed_file_snapshot: str,
    created_at: str,
) -> dict

record_stage_result(
    manifest: dict,
    stage_result: StageResult,
) -> dict

write_manifest(path: Path, manifest: dict) -> None
read_manifest(path: Path) -> dict
```

Keep this simple.

Do not create a complex manifest class unless already needed.

---

# Orchestrator Function

Implement in:

```text
farmles_harvester/orchestrator/run_pipeline.py
```

Required function:

```python
run_pipeline(
    seed_file: Path,
    tag: str,
    runs_dir: Path,
    config: dict | None = None,
    fetcher=None,
) -> Path
```

Return:

```text
Path to the created run folder
```

## Run ID Derivation

```python
run_id = f"{timestamp}_{tag}"
```

where `timestamp` follows the format `YYYY-MM-DD_HHMMSS`. The run folder is `runs_dir / run_id`.

## Responsibilities

`run_pipeline()` must:

1. Create run folder.
2. Copy seed file into run folder as `seed_urls.txt`.
3. Create initial `manifest.json`.
4. Create `StagePaths` for Stage 00.
5. Call `run_normalize_source_leads(input_path=run_dir / "seed_urls.txt", ...)`.
6. Record Stage 00 `StageResult` in manifest.
7. Create `StagePaths` for Stage 01.
8. Call `run_validate_urls()`.
9. Record Stage 01 `StageResult`.
10. Repeat for Stage 02, Stage 03, and Stage 04.
11. If any stage returns `status = "failed"`, record it in the manifest then raise `PipelineError`.
12. Return the run folder path on success.

## Stage Order

Run exactly:

```text
00_normalize_source_leads
01_validate_urls
02_discover_links
03_score_candidate_urls
04_generate_markdown_pages
```

## StagePath Construction

Use:

```python
StagePaths.for_stage(
    run_dir=run_dir,
    stage_number="00",
    artifact_name="normalized_source_leads",
)
```

Then:

```text
01 + validated_sources
02 + discovered_links
03 + candidate_urls
04 + markdown_pages
```

---

# Stage Inputs and Outputs

## Stage 00

Input:

```text
seed_urls.txt
```

Output:

```text
00_normalized_source_leads.jsonl
```

## Stage 01

Input:

```text
00_normalized_source_leads.jsonl
```

Output:

```text
01_validated_sources.jsonl
```

## Stage 02

Input:

```text
01_validated_sources.jsonl
```

Output:

```text
02_discovered_links.jsonl
```

## Stage 03

Input:

```text
02_discovered_links.jsonl
```

Output:

```text
03_candidate_urls.jsonl
```

## Stage 04

Input:

```text
03_candidate_urls.jsonl
```

Output:

```text
04_markdown_pages.jsonl
generated_wiki/
```

---

# Fetcher Injection

The orchestrator should accept an optional `fetcher`.

If provided, pass it to stages that need fetching:

```text
01_validate_urls
02_discover_links
04_generate_markdown_pages
```

Automated tests must use a fake fetcher.

Do not use real internet in tests.

If no fetcher is provided, production code may use the default real fetcher if already implemented. If no real fetcher exists yet, fail clearly with a helpful error.

---

# Failure Handling

For v1:

```text
If any stage returns status = failed:
  - Record the failed StageResult in manifest.
  - Write the manifest to disk.
  - Leave the run folder and artifacts written so far.
  - Raise PipelineError(message, stage_id=result.stage_id, run_dir=run_dir).
```

Do not continue to later stages after a failed stage.

If a stage completes with some per-record errors but returns `status = "completed"`, continue to the next stage.

---

# CLI Implementation

Implement in:

```text
farmles_harvester/cli.py
```

The CLI should:

1. Parse arguments.
2. Call `run_pipeline()`.
3. On success: print the created run folder path and exit 0.
4. On `PipelineError`: print the stage ID and run folder, then exit with status 1.

Example success output:

```text
Run completed: runs/2026-05-17_132400_smoke-test
```

Example failure output:

```text
Run failed at stage: 01_validate_urls
Run folder: runs/2026-05-17_132400_smoke-test
```

Do not print excessive logs in v1.

---

# Required Tests

## Unit Tests for Manifest

Create:

```text
tests/unit/test_manifest.py
```

Required tests:

1. `create_initial_manifest()` returns required top-level fields.
2. `record_stage_result()` adds result under `stages`.
3. `record_stage_result()` appends to `execution_log`.
4. `write_manifest()` writes valid JSON.
5. `read_manifest()` reads the same JSON back.

---

## Harness Tests for Orchestrator

Create:

```text
tests/harness/test_orchestrator.py
```

Use `tmp_path` and fake fetcher.

### Test 1: creates run folder

Given a seed file and tag, `run_pipeline()` creates a run folder under `runs_dir`.

### Test 2: copies seed file snapshot

Verify:

```text
run_dir/seed_urls.txt
```

exists and matches the original seed file content.

### Test 3: writes manifest

Verify:

```text
run_dir/manifest.json
```

exists and is valid JSON.

### Test 4: runs stages in order

After a successful run, manifest `execution_log` should contain stage IDs in order:

```text
00_normalize_source_leads
01_validate_urls
02_discover_links
03_score_candidate_urls
04_generate_markdown_pages
```

### Test 5: writes expected artifacts

Verify run folder contains:

```text
00_normalized_source_leads.jsonl
01_validated_sources.jsonl
02_discovered_links.jsonl
03_candidate_urls.jsonl
04_markdown_pages.jsonl
generated_wiki/
```

### Test 6: manifest records each StageResult

Verify manifest contains entries under `stages` for all five stages.

### Test 7: uses fake fetcher, no real network

Use fake fetcher responses for:

```text
validate_urls
discover_links
generate_markdown_pages
```

Assert the run completes without real network.

### Test 8: generated_wiki exists

Verify:

```text
run_dir/generated_wiki/
```

exists and contains at least one lead folder when candidate URLs are selected.

### Test 9: stops on failed stage

Use a test double or monkeypatch a stage to return `StageResult(status="failed")`.

Expected:

```text
pipeline stops
later stages do not run
manifest records failed stage
```

### Test 10: CLI parses arguments

If practical, test CLI main with monkeypatch/capsys or subprocess.

Verify:

```text
farmles_harvester --seed-file ... --tag ...
```

calls pipeline and reports run folder.

Keep this test simple.

---

# Integration Fixture

Use a tiny seed file and fake HTML.

Example seed file:

```text
https://apex.example/
```

Fake fetcher should provide:

## For validation

```text
https://apex.example/
→ 200 text/html
```

## For discovery

Homepage HTML:

```html
<h1>Apex Farmers Market</h1>
<a href="/vendors">Vendors</a>
<a href="/visit">Visit Us</a>
<a href="/privacy-policy">Privacy Policy</a>
```

## For markdown generation

Selected URLs:

```text
https://apex.example/vendors
https://apex.example/visit
```

Return simple HTML with facts.

This proves the full local pipeline path works.

---

# Non-Responsibilities

Do not implement:

- `farmles_wiki` import
- Git/GitHub branch or PR flow
- SQL export
- LLM fact extraction
- real URL smoke test
- scheduler
- background jobs
- multi-run coordination

Sprint 9 is only:

```text
minimal local orchestrator
CLI
manifest
end-to-end fake-fetcher pipeline test
```

---

# Acceptance Criteria

Sprint 9 is complete when:

1. CLI entry point exists.
2. `run_pipeline()` exists.
3. Run folder is created.
4. Seed file is copied into the run folder.
5. `manifest.json` is created.
6. Stage 00 through Stage 04 are called in order.
7. Each `StageResult` is recorded in the manifest.
8. Pipeline stops on failed stage.
9. `generated_wiki/` is produced for successful test data.
10. Unit tests for manifest pass.
11. Harness tests for orchestrator pass.
12. Tests use fake fetcher and do not require internet.
13. Existing stage tests still pass.
14. No wiki import, GitHub, SQL, or LLM functionality is added.

---

# Output Expected From Agent

When finished, report:

1. Files created or modified.
2. CLI implemented.
3. Orchestrator implemented.
4. Manifest helper implemented.
5. Tests added.
6. Test command used.
7. Test result.
8. Any assumptions or deferred work.
