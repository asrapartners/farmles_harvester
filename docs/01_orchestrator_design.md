# Pipeline Orchestrator Design

The orchestrator is the top-level controller for a farmles harvester run. It sequences two pipelines that execute in order: the static pipeline handles all pages reachable by plain HTTP; the dynamic pipeline follows up with pages that require browser-based rendering.

```
seed_urls.txt
      │
      ▼
┌──────────────────────────────────────┐       ┌──────────────────────────┐
│           Static Pipeline             │─write─►     url_registry.db      │
│  00 → 01 → 02 → 03 → 04 → 05 → 06   │ after  │  (stages 01, 03, 04, 06) │
└──────────────────────────────────────┘  each  └────────────┬─────────────┘
                                          stage               │
                                                  orchestrator queries
                                                  dynamic_js candidates
                                                              │
                                                              ▼
                                          ┌───────────────────────────────┐
                                          │       Dynamic Pipeline         │
                                          │  browser-fetch (crawl4ai)     │
                                          │  → strip boilerplate          │
                                          │  → update registry            │
                                          └───────────────────────────────┘
                                                              │
                                                              ▼
                                               generated_wiki/sources/<slug>/
```

See [`overview.md`](overview.md) for the system-level view of both pipelines.

---

## Static Pipeline

### Responsibilities

The orchestrator owns:

- CLI arguments
- Run folder creation — creates the output folder with `<timestamp>_<user_tag>`
- `manifest.json` — creates at start, records each `StageResult` as stages complete
- `StagePaths` — creates the three artifact paths for each stage (output, summary, errors)
- Registry lifecycle — opens one `UrlRegistry` at the start, closes it in a `finally` block
- Stage sequencing — calls each stage in order, stops on failure

Each stage returns a `StageResult`. The orchestrator writes it into `manifest.json`. Stages never write directly to `manifest.json` and never construct their own paths.

### File-Based Data Passing

Every stage reads from a JSONL file produced by the previous stage and writes its own JSONL output to the run directory. There is no in-memory handoff between stages.

**File naming convention:**

```
{stage_number}_{artifact_name}.jsonl          ← main output
{stage_number}_{artifact_name}_summary.json   ← stage summary
{stage_number}_{artifact_name}_errors.jsonl   ← processing errors
```

The orchestrator creates a [`StagePaths`](../farmles_harvester/pipeline/stage_paths.py) for each stage via `StagePaths.for_stage(run_dir, stage_number, artifact_name)` and passes the previous stage's `output_path` as the next stage's `input_path`:

```python
paths_02 = StagePaths.for_stage(run_dir, "02", "discovered_links")

run_discover_links(
    input_path=paths_01.output_path,   # 01_validated_sources.jsonl
    stage_paths=paths_02,              # owns 02_discovered_links.*
    ...
)
```

### Stage Artifacts — Summary and Errors

See [`reference/pipeline_artifacts.md`](reference/pipeline_artifacts.md) for schemas and a full run directory layout.

**`{stage}_summary.json`** — record counts by outcome, timestamps, and stage identity. Folded into `manifest.json` via `StageResult`.

**`{stage}_errors.jsonl`** — one record per input the stage could not handle at all (missing fields, unhandled exceptions). Routine failures (404, timeout, low score) appear in the main JSONL with a status field, not here.

### Implementation

**Entry point:** [`cli.py`](../farmles_harvester/cli.py) — `main()` parses CLI args, builds config, and calls `run_pipeline()`

**Orchestrator:** [`orchestrator/run_pipeline.py`](../farmles_harvester/orchestrator/run_pipeline.py) — owns run-dir creation, stage sequencing, manifest updates, and registry lifecycle

**Call sequence:**

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
[`orchestrator/registry_ingest.py`](../farmles_harvester/orchestrator/registry_ingest.py) — called after stages 01, 03, 04, 06. See [`url_registry/url_registry.md`](url_registry/url_registry.md) for details.

### UrlRegistry Integration

[`registry/url_registry.py`](../farmles_harvester/registry/url_registry.py) is a SQLite-backed persistent store for tracking URLs across runs. The orchestrator instantiates one `UrlRegistry` at the start of `run_pipeline()` and closes it at the end. The default path is `{run_dir}/url_registry.db`; callers can supply a shared path to reuse the registry across multiple runs (required for fast mode to take effect).

**Reads** happen *during* stage execution and only when `fast_mode: true` is set in config and a cross-run registry is provided. **Writes** happen *after* each stage via `orchestrator/registry_ingest.py`. All ingestion calls are non-fatal — a failure warns but does not stop the pipeline.

| Stage | Direction | When | Operation | Purpose |
|---|---|---|---|---|
| 01 — Validate URLs | WRITE | After stage | `upsert()` + `record_outcome(permanent)` | Record seed URLs that failed validation as permanent failures |
| 02 — Discover Links | READ | During stage (fast mode only) | `get(url)` → `evaluate_url_strength()` | Skip crawling internal links already known as weak or permanently failed |
| 03 — Score Candidate URLs | WRITE | After stage | `upsert_many()` + `record_source()` | Persist discovered URLs with candidate scores and source mappings |
| 04 — Generate Markdown Pages | READ | During stage (fast mode only) | `get_many(urls)` → `evaluate_markdown_strength()` | Skip re-fetching candidates that already have sufficient markdown |
| 04 — Generate Markdown Pages | WRITE | After stage | `record_outcome()` + `record_markdown_outcome()` | Record HTTP fetch results and markdown word counts/paths |
| 06 — Score Source Relevance | WRITE | After stage | `upsert_source_many()` | Persist source-level relevance labels and keyword stats |

Fast-mode decision logic lives in [`registry/evaluation.py`](../farmles_harvester/registry/evaluation.py): `evaluate_url_strength()` (stage 02) and `evaluate_markdown_strength()` (stage 04).

### Flow Diagram

Solid arrows are **writes** (post-stage ingestion via `registry_ingest.py`). Dashed arrows are **reads** (fast-mode lookups during stage execution).

```mermaid
flowchart TD
    Input([seed_urls.txt])

    S00["**00** · Normalize Source Leads"]
    S01["**01** · Validate URLs"]
    S02["**02** · Discover Links"]
    S03["**03** · Score Candidate URLs"]
    S04["**04** · Generate Markdown Pages"]
    S05["**05** · Strip Boilerplate Blocks"]
    S06["**06** · Score Source Relevance"]

    REG[("url_registry\n─────────────\nurls\nurl_sources\nsources")]

    Input --> S00 --> S01 --> S02 --> S03 --> S04 --> S05 --> S06

    S01 -->|"WRITE · ingest_validation_failures\nupsert + record_outcome(permanent)"| REG
    REG -.->|"READ · fast mode only\nget → evaluate_url_strength"| S02
    S03 -->|"WRITE · ingest_urls\nupsert_many + record_source"| REG
    REG -.->|"READ · fast mode only\nget_many → evaluate_markdown_strength"| S04
    S04 -->|"WRITE · ingest_fetch_outcomes\nrecord_outcome"| REG
    S04 -->|"WRITE · ingest_markdown_outcomes\nrecord_markdown_outcome"| REG
    S06 -->|"WRITE · ingest_source_relevance\nupsert_source_many"| REG
```

---

## Dynamic Pipeline

### Responsibilities

The orchestrator is responsible for creating the input context for the dynamic pipeline. After the static pipeline completes, it queries the registry for all pages the static pipeline could not fetch — pages flagged as `render_type = dynamic_js` with `markdown_status = not_attempted` — and passes that batch to `run_dynamic_pipeline()`.

By the time the static pipeline finishes, the registry holds everything the dynamic pipeline needs: the URL, the `md_path` already assigned by stage 04, and the source slug. The orchestrator's job is to collect and hand it over — no path computation or discovery is needed.

### Handoff

```python
run_pipeline(...)           # static pipeline completes

dynamic_candidates = registry.query(
    where="render_type = 'dynamic_js' AND markdown_status = 'not_attempted'"
)
run_dynamic_pipeline(candidates=dynamic_candidates, run_dir=run_dir, registry=registry)
```

The dynamic pipeline receives a fully resolved batch and is responsible for browser-fetching, boilerplate stripping, and updating the registry. See [`dynamic_pipeline/overview.md`](dynamic_pipeline/overview.md) for the full design.
