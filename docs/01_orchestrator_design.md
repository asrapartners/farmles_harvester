# Pipeline Orchestrator Design

## Purpose

The orchestrator is the top level controller for one 'farmles_harvester' run of a pipeline. It calls each stage
of the pipeline in order with the input and "StagePaths" and records the result returned.

It owns

- CLI arguments
- run folder creation if required.
- creates the output folder with <timestamp>_<user_tag>
- creates the `manifest.json` with run level metadata.

For each stage the orchestrator creates StagePaths. This has 
- absolute path to the output file
- absolute path to the summary file
- absolute path to the error file

For example for stage 00:

```
StagePaths(
    output_path=Path("/work/farmles_harvester/runs/2026-05-17_132400_initial-import/00_normalized_source_leads.jsonl"),
    summary_path=Path("/work/farmles_harvester/runs/2026-05-17_132400_initial-import/00_normalized_source_leads_summary.json"),
    errors_path=Path("/work/farmles_harvester/runs/2026-05-17_132400_initial-import/00_normalized_source_leads_errors.jsonl"),
)
```

Each stage returns StageResult
The orchestrator writes that result into manifest.json. Stages never write directly to `manifest.json`. use relative paths to the run directory inside `manifest.json`.
{
  "produced_artifacts": ["00_normalized_source_leads.jsonl"],
  "summary_artifact": "00_normalized_source_leads_summary.json",
  "error_artifact": "00_normalized_source_leads_errors.jsonl"
}
If a stage fails then stop the run. Record failed StageResult in manifest.json and leave the artifacts in the run dir.

## Implementation

**Entry point:** [`cli.py`](../farmles_harvester/cli.py) — `main()` parses CLI args, builds config, and calls `run_pipeline()`

**Orchestrator:** [`orchestrator/run_pipeline.py`](../farmles_harvester/orchestrator/run_pipeline.py) — `run_pipeline()` owns run-dir creation, stage sequencing, manifest updates, and registry lifecycle

**Call sequence (stages):**

| Stage | Source file | Entry function |
|---|---|---|
| 00 | [`stages/normalize_source_leads.py`](../farmles_harvester/stages/normalize_source_leads.py) | `run_normalize_source_leads()` |
| 01 | [`stages/validate_urls.py`](../farmles_harvester/stages/validate_urls.py) | `run_validate_urls()` |
| 02 | [`stages/discover_links.py`](../farmles_harvester/stages/discover_links.py) | `run_discover_links()` |
| 03 | [`stages/score_candidate_urls.py`](../farmles_harvester/stages/score_candidate_urls.py) | `run_score_candidate_urls()` |
| 04 | [`stages/generate_markdown_pages.py`](../farmles_harvester/stages/generate_markdown_pages.py) | `run_generate_markdown_pages()` |
| 05 | [`stages/strip_boilerplate_blocks.py`](../farmles_harvester/stages/strip_boilerplate_blocks.py) | `run_strip_boilerplate_blocks()` |
| 06 | [`stages/score_source_relevance.py`](../farmles_harvester/stages/score_source_relevance.py) | `run_score_source_relevance()` |

**Supporting modules:**
- [`orchestrator/manifest.py`](../farmles_harvester/orchestrator/manifest.py) — `create_initial_manifest()`, `record_stage_result()`
- [`pipeline/stage_paths.py`](../farmles_harvester/pipeline/stage_paths.py) — `StagePaths.for_stage()`
- [`pipeline/stage_result.py`](../farmles_harvester/pipeline/stage_result.py) — `StageResult` dataclass

**Registry ingestion** (non-fatal — warns but does not stop the pipeline):
[`orchestrator/registry_ingest.py`](../farmles_harvester/orchestrator/registry_ingest.py) — called after stages 01, 03, 04, 06. See [`docs/pipeline/registry_integration.md`](pipeline/registry_integration.md) for details.
