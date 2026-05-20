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
