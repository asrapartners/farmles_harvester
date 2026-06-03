# Strip Boilerplate Blocks Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

The `strip_boilerplate_blocks` stage removes repeated boilerplate from markdown files that were written by stage 04 — navigation fragments, footer text, and cookie notices that `clean_html` reduced but did not fully eliminate.

This stage answers:

> Which markdown blocks appear on nearly every page of this source and should be treated as site chrome, not content?

It detects repetition per source domain and strips matching blocks in-place from the markdown files.

It does **not** fetch pages.  
It does **not** re-score or re-rank candidates.  
It does **not** rewrite or summarize content.  
It does **not** remove blocks that are unique to a page.  
It does **not** run if a source has fewer than `min_files_for_fingerprint` markdown files.

---

## Consumed Artifact

```text
04_markdown_pages.jsonl
```

Only records with `fetch_status = fetched` and a populated `markdown_path` are processed. All others are skipped silently.

| Field | Required | How this stage uses it |
|---|---|---|
| `source_slug` | yes | Groups files by source domain for fingerprinting |
| `markdown_path` | yes | Resolved to an absolute path; file is read and optionally rewritten |
| `fetch_status` | yes | Only `fetched` records are processed |
| `run_id` | yes | Preserved in output record |
| all other fields | no | Ignored |

---

## Core Responsibility

For each source group ([`stages/strip_boilerplate_blocks.py`](../../farmles_harvester/stages/strip_boilerplate_blocks.py) → `run_strip_boilerplate_blocks()`):

1. Read all records from `04_markdown_pages.jsonl`; filter to `fetch_status = fetched` with a valid `markdown_path`.
2. Group markdown file paths by `source_slug`.
3. For each source group, read all markdown file contents and build a block fingerprint via `build_md_fingerprint()` ([`wiki/markdown_cleaner.py`](../../farmles_harvester/wiki/markdown_cleaner.py)) — a set of block hashes that appear in ≥ `boilerplate_threshold` of the source's files.
4. Skip fingerprinting if the source has fewer than `min_files_for_fingerprint` files; the fingerprint is empty and no blocks are removed.
5. For each markdown file in the group, strip fingerprinted blocks via `strip_md_fingerprint()` ([`wiki/markdown_cleaner.py`](../../farmles_harvester/wiki/markdown_cleaner.py)).
6. If the file changed, rewrite it in-place under `generated_wiki/`.
7. Append one record per file to `05_stripped_pages.jsonl` via `JsonlWriter` ([`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py)).

---

## Fingerprinting Algorithm

`build_md_fingerprint(contents, threshold, min_files)` ([`wiki/markdown_cleaner.py`](../../farmles_harvester/wiki/markdown_cleaner.py)):

1. Split each file into paragraph blocks (double-newline boundaries).
2. Normalize each block — strip links, images, heading markers, and markdown formatting — then hash the result.
3. Count how many distinct files each block hash appears in.
4. Return hashes where `count / total_files ≥ threshold` as the fingerprint.

`strip_md_fingerprint(content, fingerprint)` removes every block whose normalized hash is in the fingerprint.

The fingerprint is computed fresh per run, per source. It is not stored between runs.

---

## Input Filtering Rules

Only records with both `fetch_status = fetched` and a non-empty `markdown_path` enter processing. Fetch-failed and skipped records are ignored and do not appear in the output JSONL.

Sources with fewer than `min_files_for_fingerprint` files are processed but produce no block removals — the empty fingerprint means no blocks match.

---

## Output Record Contract

Each line in `05_stripped_pages.jsonl` is one JSON object — one record per markdown file that was evaluated (modified or not).

| Field | Required | Description |
|---|---|---|
| `run_id` | yes | Run identifier, injected by the harness |
| `source_slug` | yes | Source domain slug; identifies the wiki subfolder |
| `markdown_path` | yes | Relative path to the markdown file, e.g. `generated_wiki/sources/apexfarmersmarket-com/vendors/index.md` |
| `blocks_removed` | yes | Number of boilerplate blocks stripped from this file |
| `content_hash` | yes | `sha256:<hex>` of the file content after stripping |
| `modified` | yes | `true` if the file was rewritten; `false` if no blocks matched |
| `processed_at` | yes | ISO-8601 timestamp |

Example:

```json
{
  "run_id": "2026-05-17_132400_initial-import",
  "source_slug": "apexfarmersmarket-com",
  "markdown_path": "generated_wiki/sources/apexfarmersmarket-com/vendors/index.md",
  "blocks_removed": 2,
  "content_hash": "sha256:def456",
  "modified": true,
  "processed_at": "2026-05-17T13:30:00Z"
}
```

---

## Output Policy

Write one record per markdown file evaluated, regardless of whether it was modified.

Files from sources below `min_files_for_fingerprint` are written with `blocks_removed = 0` and `modified = false`.

Markdown files are rewritten in-place under `generated_wiki/`. Stage 04's output JSONL is not modified — the updated content hash is only in the stage 05 output.

---

## Error Artifact Contract

`05_stripped_pages_errors.jsonl` — reserved for unexpected failures (e.g., unreadable files). Under normal conditions this file is empty.

| Field | Description |
|---|---|
| `run_id` | Run identifier |
| `stage_name` | Always `strip_boilerplate_blocks` |
| `source_slug` | From the input record, if present |
| `markdown_path` | From the input record, if present |
| `error_type` | e.g. `read_error`, `write_error` |
| `message` | Human-readable description of the failure |
| `retryable` | Boolean |
| `created_at` | ISO-8601 timestamp |

---

## Summary Artifact Contract

`05_stripped_pages_summary.json` — one JSON object written after the stage completes.

| Field | Description |
|---|---|
| `stage_name` | `strip_boilerplate_blocks` |
| `stage_number` | `05` |
| `run_id` | Run identifier |
| `total_files` | Total markdown files evaluated |
| `sources_processed` | Number of distinct source slugs processed |
| `files_modified` | Files where at least one block was stripped |
| `total_blocks_removed` | Sum of `blocks_removed` across all files |
| `started_at` | ISO-8601 timestamp |
| `completed_at` | ISO-8601 timestamp |

---

## Implementation

**Entry function:** `run_strip_boilerplate_blocks(input_path, stage_paths, run_id, config)`
[`stages/strip_boilerplate_blocks.py`](../../farmles_harvester/stages/strip_boilerplate_blocks.py)

Call sequence:
1. `read_jsonl()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — reads all stage 04 records
2. `build_md_fingerprint(contents, threshold, min_files)` — [`wiki/markdown_cleaner.py`](../../farmles_harvester/wiki/markdown_cleaner.py) — builds per-source boilerplate fingerprint
3. `strip_md_fingerprint(content, fingerprint)` — [`wiki/markdown_cleaner.py`](../../farmles_harvester/wiki/markdown_cleaner.py) — strips matching blocks from each file
4. `Path.write_text()` — rewrites the markdown file in-place if modified
5. `JsonlWriter` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — writes one output record per file

Key helpers:
- `normalize_md_block()` — [`wiki/markdown_cleaner.py`](../../farmles_harvester/wiki/markdown_cleaner.py) — strips formatting before hashing so minor rendering differences don't prevent block matching

---

## Configuration

Recommended config values:

```json
{
  "boilerplate_threshold": 0.8,
  "min_files_for_fingerprint": 3
}
```

`boilerplate_threshold`: fraction of a source's files a block must appear in to be considered boilerplate (0.0–1.0). Lower values remove more aggressively.

`min_files_for_fingerprint`: minimum number of fetched pages a source must have before fingerprinting is attempted. Sources below this threshold are passed through unchanged.

---

## Registry Integration

This stage does not write to the registry directly. The updated `content_hash` values in `05_stripped_pages.jsonl` are used by stage 06 to read the post-stripped markdown from disk.

---

## Definition of Done

This stage is complete when:

1. The stage reads `04_markdown_pages.jsonl`.
2. Only `fetch_status = fetched` records with a valid `markdown_path` are processed.
3. Markdown files are grouped by `source_slug`.
4. A boilerplate fingerprint is built per source group using `build_md_fingerprint()`.
5. Sources with fewer than `min_files_for_fingerprint` files are passed through without modification.
6. Matching blocks are stripped from each file via `strip_md_fingerprint()`.
7. Modified files are rewritten in-place; unmodified files are left untouched.
8. The stage writes `05_stripped_pages.jsonl` with one record per file.
9. Unit tests cover `build_md_fingerprint()` (threshold boundary, min_files guard), `strip_md_fingerprint()` (blocks removed, unmodified passthrough), and `normalize_md_block()`.
10. The stage does not fetch pages, re-score candidates, or call an LLM.
