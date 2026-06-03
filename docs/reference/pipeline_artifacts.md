# Pipeline Artifacts Reference

Every file the pipeline writes to disk — where it lives, who owns it, and what it contains.

---

## Run directory layout

A complete run produces the following files:

```
runs/2026-05-17_132400_initial-import/
│
│  ── meta ──────────────────────────────────────────────────────
├── manifest.json                       ← run-level ledger (orchestrator)
├── url_registry.db                     ← SQLite cross-run store (optional)
│
│  ── stage 00 ───────────────────────────────────────────────────
├── 00_normalized_source_leads.jsonl
├── 00_normalized_source_leads_summary.json
├── 00_normalized_source_leads_errors.jsonl
│
│  ── stage 01 ───────────────────────────────────────────────────
├── 01_validated_sources.jsonl
├── 01_validated_sources_summary.json
├── 01_validated_sources_errors.jsonl
│
│  ── stages 02–06 follow the same pattern ───────────────────────
│  (02_discovered_links, 03_candidate_urls, 04_markdown_pages,
│   05_stripped_pages, 06_source_relevance)
│
│  ── wiki output ─────────────────────────────────────────────────
└── generated_wiki/
    └── sources/
        └── <source_slug>/
            ├── source_metadata.json    ← per-source meta (stage 04 + 06)
            └── *.md                    ← fetched markdown pages (stage 04)
```

---

## `manifest.json`

**Location:** `<run_dir>/manifest.json`  
**Owner:** [`orchestrator/manifest.py`](../../farmles_harvester/orchestrator/manifest.py) — written by the orchestrator, never by stages.  
**Purpose:** Run-level ledger. Records which stages ran, their outcomes, and the artifact filenames they produced.

```json
{
  "run_id": "2026-05-17_132400_initial-import",
  "created_at": "2026-05-17T13:24:00.123456+00:00",
  "tag": "initial-import",
  "seed_file_snapshot": "seed_urls.txt",
  "stages": {
    "01_validate_urls": {
      "stage_id": "01_validate_urls",
      "stage_number": "01",
      "stage_name": "validate_urls",
      "status": "completed",
      "consumed_artifacts": ["00_normalized_source_leads.jsonl"],
      "produced_artifacts": ["01_validated_sources.jsonl"],
      "summary_artifact": "01_validated_sources_summary.json",
      "error_artifact": "01_validated_sources_errors.jsonl",
      "counts": { "valid_count": 12, "broken_count": 1, ... },
      "started_at": "2026-05-17T13:24:05+00:00",
      "completed_at": "2026-05-17T13:24:18+00:00",
      "metadata": {}
    }
  },
  "execution_log": [
    {
      "sequence": 1,
      "stage_id": "01_validate_urls",
      "status": "completed",
      "started_at": "...",
      "completed_at": "..."
    }
  ]
}
```

All artifact paths in `manifest.json` are relative to the run directory.

---

## `{stage}_summary.json`

**Location:** `<run_dir>/{stage}_{artifact}_summary.json`  
**Owner:** The stage harness — written after the stage completes.  
**Purpose:** Quick-scan observability. Contains per-outcome record counts plus start/end timestamps. The orchestrator folds the counts into `manifest.json` via `StageResult`; the file itself stays in the run dir for direct inspection.

```json
{
  "stage_name": "validate_urls",
  "stage_number": "01",
  "run_id": "2026-05-17_132400_initial-import",
  "input_records": 13,
  "output_records": 12,
  "error_records": 0,
  "valid_count": 10,
  "redirected_count": 2,
  "broken_count": 1,
  "blocked_count": 0,
  "timeout_count": 0,
  "started_at": "2026-05-17T13:24:05+00:00",
  "completed_at": "2026-05-17T13:24:18+00:00"
}
```

Count field names vary by stage — each stage adds fields relevant to its own outcome categories.

---

## `{stage}_errors.jsonl`

**Location:** `<run_dir>/{stage}_{artifact}_errors.jsonl`  
**Owner:** The stage harness.  
**Purpose:** Records inputs the stage could not handle at all — missing required fields, unhandled exceptions, parser crashes. Routine failures (404s, timeouts, low scores, skipped records) are **not** errors; they appear in the main output JSONL with an appropriate `status` field.

The rule: if the stage knows what happened, it is an output record. If the stage could not handle it at all, it is an error record.

Each error record is a single JSON object containing at minimum `input` (the original record that caused the failure) and `error` (a message or exception string). Structure varies by stage.

---

## `source_metadata.json`

**Location:** `<run_dir>/generated_wiki/sources/<source_slug>/source_metadata.json`  
**Owner:** Stage 04 (`generate_markdown_pages`) writes the initial file; stage 06 (`score_source_relevance`) patches `relevance_label` and `relevance_score` in-place.  
**Purpose:** Makes each source folder self-describing — one place to look up what a source is, what pages were fetched from it, and how relevant the source turned out to be.

```json
{
  "source_slug": "apex-example-com",
  "input_url": "https://apex-example.com",
  "normalized_url": "https://apex-example.com/",
  "final_url": "https://apex-example.com/",
  "relevance_label": "confirmed",
  "relevance_score": 80,
  "pages": [
    {
      "url": "https://apex-example.com/vendors",
      "link_text": "Vendors",
      "candidate_type": "vendor_page",
      "candidate_status": "fetched",
      "candidate_score": 80,
      "markdown_path": "vendors.md"
    }
  ]
}
```

`relevance_label` and `relevance_score` are absent until stage 06 runs. All other fields are stable after stage 04.

`markdown_path` values are relative to the source's wiki folder (`generated_wiki/sources/<source_slug>/`).

---

## `url_registry.db`

**Location:** `<run_dir>/url_registry.db` by default; a shared path can be supplied to `run_pipeline()` to reuse the registry across runs (required for fast mode).  
**Owner:** [`registry/url_registry.py`](../../farmles_harvester/registry/url_registry.py) — opened by the orchestrator at the start of `run_pipeline()` and closed in a `finally` block.  
**Purpose:** SQLite-backed cross-run store that tracks URLs, fetch outcomes, markdown quality, and source-level relevance labels so subsequent runs can skip work already done.

See [`url_registry/url_registry.md`](../url_registry/url_registry.md) for the full stage-by-stage read/write map, and [`url_registry/fast_mode.md`](../url_registry/fast_mode.md) for how the registry drives skip decisions.
