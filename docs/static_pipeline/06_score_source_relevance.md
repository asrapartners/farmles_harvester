# Score Source Relevance Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

The `score_source_relevance` stage reads the cleaned markdown files produced by stages 04 and 05 and decides how likely each source website is to be a genuine farmers market.

This stage answers:

> Is this source actually a farmers market, or did it just surface as a false positive?

It scores each source by counting market-relevant keyword hits across all of its markdown pages and assigns a confidence label.

It does **not** fetch pages.  
It does **not** modify markdown files.  
It does **not** call an LLM.  
It does **not** score individual candidate pages — it scores the source as a whole.

---

## Consumed Artifact

```text
05_stripped_pages.jsonl
```

Each input record points to a markdown file that has been fetched and boilerplate-stripped. The stage reads the file contents from disk using `markdown_path`.

| Field | Required | How this stage uses it |
|---|---|---|
| `source_slug` | yes | Groups files by source domain for per-source scoring |
| `markdown_path` | yes | Resolved to an absolute path; file content is read for scoring |
| `run_id` | yes | Preserved in output record |
| all other fields | no | Ignored |

---

## Core Responsibility

For each source group ([`stages/score_source_relevance.py`](../../farmles_harvester/stages/score_source_relevance.py) → `run_score_source_relevance()`):

1. Read all records from `05_stripped_pages.jsonl`; group markdown file paths by `source_slug`.
2. Read the markdown text from disk for each file in the group.
3. Score the source via `score_source(md_texts, config)` ([`wiki/relevance_scorer.py`](../../farmles_harvester/wiki/relevance_scorer.py)) — counts keyword hits, negative signal hits, and total word count across all pages.
4. Assign a `relevance_label` — the highest confidence label reached by any single page in the source.
5. Compute `relevance_score` — `max(0, keyword_hits × 10 − negative_hits × 5)` across all pages.
6. Append one record per source to `06_source_relevance.jsonl` via `JsonlWriter` ([`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py)).
7. Patch `source_metadata.json` in the source's wiki folder with `relevance_label` and `relevance_score` so the folder is self-describing.

---

## Scoring Model

`score_source()` ([`wiki/relevance_scorer.py`](../../farmles_harvester/wiki/relevance_scorer.py)) scores each page independently then promotes the source to the best label found on any page.

### Market keywords (positive signal)

`farmer`, `farmers`, `market`, `vendor`, `vendors`, `produce`, `organic`, `food`, `harvest`, `seasonal`, `booth`, `stall`, `fresh`, `local`, `grower`, `growers`, `artisan`, `farmstand`, `farm`, `csa`, `agri`

Each occurrence adds to `keyword_hits`. Score contribution per page: `keyword_hits × 10`.

### Non-market signals (negative signal)

`township`, `municipality`, `zoning`, `ordinance`, `government`, `council`, `commissioner`, `supervisor`, `police`, `fire`, `emergency`, `utilities`

Each distinct word found (not per occurrence) adds to `negative_hits`. Score penalty: `negative_hits × 5`.

### Label thresholds (per page)

| Label | Condition |
|---|---|
| `confirmed` | page score ≥ 30 **and** word count ≥ 200 |
| `likely` | page score ≥ 10 **and** word count ≥ 50 |
| `uncertain` | page score ≥ 1 **or** word count ≥ 20 |
| `low_confidence` | none of the above |

The source label is the highest label reached by any single page. One strong page is enough to mark the source `confirmed`.

---

## Output Record Contract

Each line in `06_source_relevance.jsonl` is one JSON object — one record per source slug.

| Field | Required | Description |
|---|---|---|
| `run_id` | yes | Run identifier, injected by the harness |
| `source_slug` | yes | Source domain slug |
| `relevance_label` | yes | `confirmed`, `likely`, `uncertain`, or `low_confidence` |
| `relevance_score` | yes | `max(0, keyword_hits × 10 − negative_hits × 5)` across all pages |
| `keyword_hits` | yes | Total market keyword occurrences across all pages |
| `negative_hits` | yes | Total distinct non-market signal words found across all pages |
| `total_word_count` | yes | Total word count across all pages |
| `page_count` | yes | Number of markdown pages scored for this source |
| `scored_at` | yes | ISO-8601 timestamp |

Example:

```json
{
  "run_id": "2026-05-17_132400_initial-import",
  "source_slug": "apexfarmersmarket-com",
  "relevance_label": "confirmed",
  "relevance_score": 140,
  "keyword_hits": 14,
  "negative_hits": 0,
  "total_word_count": 1820,
  "page_count": 4,
  "scored_at": "2026-05-17T13:35:00Z"
}
```

---

## Output Policy

Write one record per source slug to `06_source_relevance.jsonl`.

Sources where no markdown files exist on disk (all paths missing) produce no output record — they are silently skipped.

`source_metadata.json` is patched in-place inside `generated_wiki/sources/<source_slug>/` for every source that produces an output record. The patch adds `relevance_label` and `relevance_score` to the existing JSON object.

---

## Error Artifact Contract

`06_source_relevance_errors.jsonl` — reserved for unexpected failures. Under normal conditions this file is empty.

| Field | Description |
|---|---|
| `run_id` | Run identifier |
| `stage_name` | Always `score_source_relevance` |
| `source_slug` | The source being scored when the failure occurred |
| `error_type` | e.g. `read_error`, `score_error` |
| `message` | Human-readable description of the failure |
| `retryable` | Boolean |
| `created_at` | ISO-8601 timestamp |

---

## Summary Artifact Contract

`06_source_relevance_summary.json` — one JSON object written after the stage completes.

| Field | Description |
|---|---|
| `stage_name` | `score_source_relevance` |
| `stage_number` | `06` |
| `run_id` | Run identifier |
| `total_sources` | Number of source slugs scored |
| `confirmed_count` | Sources with `relevance_label = confirmed` |
| `likely_count` | Sources with `relevance_label = likely` |
| `uncertain_count` | Sources with `relevance_label = uncertain` |
| `low_confidence_count` | Sources with `relevance_label = low_confidence` |
| `started_at` | ISO-8601 timestamp |
| `completed_at` | ISO-8601 timestamp |

---

## Implementation

**Entry function:** `run_score_source_relevance(input_path, stage_paths, run_id, config)`
[`stages/score_source_relevance.py`](../../farmles_harvester/stages/score_source_relevance.py)

Call sequence:
1. `read_jsonl()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — reads all stage 05 records
2. `Path.read_text()` — reads each markdown file from disk
3. `score_source(md_texts, config)` — [`wiki/relevance_scorer.py`](../../farmles_harvester/wiki/relevance_scorer.py) — scores keyword and negative signal hits, returns label and counts
4. `JsonlWriter` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — writes one output record per source
5. `source_metadata.json` patch — writes `relevance_label` and `relevance_score` into the wiki folder

Key helpers:
- `score_md_text(text)` — [`wiki/relevance_scorer.py`](../../farmles_harvester/wiki/relevance_scorer.py) — scores a single page; strips the title line and `Source:` footer before counting
- `_label_for_page(keyword_hits, word_count, cfg)` — [`wiki/relevance_scorer.py`](../../farmles_harvester/wiki/relevance_scorer.py) — applies label thresholds to a single page

Relevance constants: `SourceRelevanceLabel` in [`constants.py`](../../farmles_harvester/constants.py)

---

## Configuration

Recommended config values:

```json
{
  "confirmed_score": 30,
  "confirmed_words": 200,
  "likely_score": 10,
  "likely_words": 50,
  "uncertain_min_score": 1,
  "uncertain_min_words": 20
}
```

All thresholds apply per page. The source label is the maximum label across all its pages.

---

## Registry Integration

After this stage completes, the orchestrator calls `ingest_source_relevance()` in [`orchestrator/registry_ingest.py`](../../farmles_harvester/orchestrator/registry_ingest.py). The stage itself does not touch the registry.

`ingest_source_relevance()` reads `06_source_relevance.jsonl` and calls `registry.upsert_source_many()`, writing `relevance_label`, `relevance_score`, `keyword_hits`, `negative_hits`, `total_word_count`, and `page_count` into the `sources` table keyed by `source_url`.

---

## Definition of Done

This stage is complete when:

1. The stage reads `05_stripped_pages.jsonl`.
2. Markdown file paths are grouped by `source_slug`.
3. Each source is scored across all its pages using `score_source()`.
4. Each source receives a `relevance_label` based on the best single-page score.
5. The stage writes `06_source_relevance.jsonl` with one record per source.
6. `source_metadata.json` is patched with `relevance_label` and `relevance_score` for each scored source.
7. Unit tests cover `score_md_text()` (keyword counting, negative signal counting, footer stripping), `_label_for_page()` (all four label thresholds), and `score_source()` (best-page promotion, multi-page aggregation).
8. The stage does not fetch pages, modify markdown content, or call an LLM.
