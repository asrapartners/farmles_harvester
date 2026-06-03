# Score Candidate Pages Pipeline Stage

_Part of the pipeline — see [Pipeline Orchestrator Design](../01_orchestrator_design.md)._

## Purpose

The `score_candidate_urls` stage takes discovered link records and decides which links are likely worth fetching in a later stage.

This stage answers:

> Which discovered links look useful enough to become candidate pages?

It uses deterministic, rule-based scoring.

It does **not** fetch pages.  
It does **not** validate whether discovered URLs return 200.  
It does **not** extract farmers market facts.  
It does **not** call an LLM.

---

## Consumed Artifact

```text
02_discovered_links.jsonl
```

Each input record represents one link discovered on a validated source page.

| Field | Required | How this stage uses it |
|---|---|---|
| `discovered_url` | yes | Scored — path segments and query keys are tokenized for signal matching |
| `link_text` | yes | Scored — text tokens feed the same signal matching as the URL |
| `is_internal` | yes | Scored — external links short-circuit immediately to `external_reference` |
| `source_lead_id` | yes | Preserved in output; used for deduplication key |
| `source_url` | yes | Preserved in output |
| `run_id` | yes | Validated; output record re-injects it from the harness `run_id` arg |
| `follow_allowed` | yes | Validated (in `DISCOVERED_LINK_REQUIRED`) but not used in scoring logic |
| `input_url` | no | Passed through to output if present |
| `normalized_url` | no | Passed through to output if present |
| all other fields | no | Ignored |

---

## Core Responsibility

For each discovered link record ([`stages/score_candidate_urls.py`](../../farmles_harvester/stages/score_candidate_urls.py) → `run_score_candidate_urls()`):

1. Read `discovered_url`, `link_text`, and `is_internal` for scoring; `source_lead_id` and `source_url` for output.
2. Apply deterministic scoring rules — `score_discovered_link(LinkRecord, config) -> CandidateScore`.
3. Assign a `candidate_score` — integer 0–100, clamped.
4. Assign a `candidate_type` — strongest matched signal family (`CandidateType` in [`constants.py`](../../farmles_harvester/constants.py)).
5. Assign a `candidate_status` — routing decision (`CandidateStatus` in [`constants.py`](../../farmles_harvester/constants.py)).
6. Record `score_reasons` — list of applied signals with point values.
7. Write all scored records (selected and rejected) to `03_candidate_urls.jsonl` via `JsonlWriter` ([`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py)).

---

## Input Filtering Rules

The stage may score all discovered link records, but it should only select records where:

```text
follow_allowed = true
is_internal = true
```

External links may be scored and recorded as rejected or external references, but they should not become fetch candidates in v1.

For v1:

```text
internal + follow_allowed = eligible for selection
external = record/reject, not selected for fetch
```

---

## Scoring Output Fields

`score_discovered_link()` ([`stages/score_candidate_urls.py`](../../farmles_harvester/stages/score_candidate_urls.py)) assigns these fields on every output record in `03_candidate_urls.jsonl`:

**`candidate_status`** — routing decision for downstream stages:

| Value | Meaning |
|---|---|
| `selected` | Score ≥ threshold; will be fetched by stage 04 |
| `rejected` | Score below threshold |
| `external_reference` | External domain; not fetched in v1 |

**`candidate_type`** — strongest signal family that drove the score:

| Value | Likely content |
|---|---|
| `vendor_page` | Vendor names, roster, product categories, or applications |
| `hours_location_page` | Hours, schedule, address, directions, or parking |
| `calendar_events_page` | Calendar, events, seasonal dates, or opening days |
| `about_contact_page` | About, contact, organization, manager, or general market info |
| `general_market_page` | Relevant to the market but not more narrowly classifiable |
| `external_reference` | External link; recorded as reference, not a v1 fetch candidate |
| `low_value_page` | Matched a hard-reject token (privacy, login, cart, …) |
| `unknown` | No strong positive or negative signal |

---

## Scoring Model

See [03_scoring_model.md](03_scoring_model.md) for the full scoring rules.

Summary:

- Score starts at 0, clamped to 0–100
- Positive signals: vendor (+40/+30), hours/schedule (+35/+25), location/visit (+35/+25), calendar/events (+30/+20), about/contact (+20/+15), market keywords (+15), internal+follow_allowed (+10)
- Negative signals: low-value paths (−100), blog/archive (−25), old year (−30), covid (−25)
- Selected threshold: 40; strong threshold: 70
- Candidate type assigned by strongest signal family: vendor > hours_location > calendar_events > about_contact > general_market > low_value > unknown

---

## Output Policy

For v1, write all scored records to `03_candidate_urls.jsonl`, including rejected records.

Reason:

This makes tuning easier because developers can inspect why links were rejected.

Each output record should clearly state:

```text
candidate_status
candidate_score
candidate_type
score_reasons
```

Later, if storage volume becomes a problem, rejected records may be moved to a separate diagnostics artifact.

---

## Deduplication Rule

Deduplicate candidate records by:

```text
source_lead_id + discovered_url
```

If duplicate records are present in input, keep the highest scoring result.

If scores tie, keep the first record.

---

## Output Record Contract

Each line in `03_candidate_urls.jsonl` is one JSON object.

| Field | Required | Description |
|---|---|---|
| `run_id` | yes | Run identifier, injected by the harness |
| `source_lead_id` | yes | Identity of the seed lead; preserved from input |
| `source_url` | yes | Seed URL that was crawled; preserved from input |
| `candidate_url` | yes | The scored URL (renamed from `discovered_url`) |
| `link_text` | yes | Anchor text of the link; preserved from input |
| `is_internal` | yes | Whether the link is on the same domain as the source |
| `candidate_score` | yes | Integer 0–100; higher means more likely to contain market data |
| `candidate_type` | yes | Strongest signal family — see [Scoring Output Fields](#scoring-output-fields) |
| `candidate_status` | yes | Routing decision (`selected`, `rejected`, `external_reference`) |
| `candidate_strength` | yes | `strong` (≥70), `medium` (≥40), `weak` (<40) |
| `score_reasons` | yes | List of scoring signals applied, e.g. `["+50 matched ['vendor']", "-30 soft penalty: blog"]` |
| `scored_at` | yes | ISO-8601 timestamp |
| `input_url` | no | Passed through from input if present |
| `normalized_url` | no | Passed through from input if present |

Example:

```json
{
  "run_id": "2026-05-16_113045_full-recrawl",
  "source_lead_id": "lead_000001",
  "source_url": "https://www.apexfarmersmarket.com/",
  "candidate_url": "https://www.apexfarmersmarket.com/vendors",
  "link_text": "Vendors",
  "is_internal": true,
  "candidate_score": 70,
  "candidate_type": "vendor_page",
  "candidate_status": "selected",
  "candidate_strength": "strong",
  "score_reasons": ["+50 matched ['vendor', 'vendors']", "+20 matched ['market']"],
  "scored_at": "2026-05-16T11:55:00Z"
}
```

---

## Error Artifact Contract

`03_candidate_urls_errors.jsonl` — one record per input the stage could not process. Malformed records produce an error and do not crash the stage.

| Field | Description |
|---|---|
| `run_id` | Run identifier |
| `stage_name` | Always `score_candidate_urls` |
| `source_lead_id` | From the input record, if present |
| `discovered_url` | From the input record, if present |
| `error_type` | e.g. `invalid_input_record` |
| `message` | Human-readable description of the failure |
| `retryable` | Boolean |
| `created_at` | ISO-8601 timestamp |

---

## Summary Artifact Contract

`03_candidate_urls_summary.json` — one JSON object written after the stage completes.

| Field | Description |
|---|---|
| `stage_name` | `score_candidate_urls` |
| `stage_number` | `03` |
| `run_id` | Run identifier |
| `input_records` | Total records read |
| `output_records` | Total records written |
| `error_records` | Records that failed processing |
| `selected_count` | Records with `candidate_status = selected` |
| `rejected_count` | Records with `candidate_status = rejected` |
| `external_reference_count` | Records with `candidate_status = external_reference` |
| `strong_candidate_count` | Records with `candidate_strength = strong` |
| `medium_candidate_count` | Records with `candidate_strength = medium` |
| `weak_candidate_count` | Records with `candidate_strength = weak` |
| `homepage_promoted_count` | Rejected homepages promoted because the source had meaningful sub-page selections |
| `program_boosted_count` | Rejected records boosted because the source linked to an authoritative program domain |
| `started_at` | ISO-8601 timestamp |
| `completed_at` | ISO-8601 timestamp |

---

## Implementation

**Entry function:** `run_score_candidate_urls(input_path, stage_paths, run_id, config)`
[`stages/score_candidate_urls.py`](../../farmles_harvester/stages/score_candidate_urls.py)

Call sequence:
1. `stream_jsonl()` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — streams discovered link records
2. `score_discovered_link(LinkRecord, config)` — local pure function — applies token-based scoring rules, returns `CandidateScore`
3. `JsonlWriter` — [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — writes all scored records (selected and rejected)

Key dataclasses (also imported by stage 02):
- `LinkRecord` — `(discovered_url, link_text, is_internal, follow_allowed)`
- `CandidateScore` — `(candidate_score, candidate_type, candidate_status, candidate_strength, score_reasons)`

Scoring constants: `CandidateType`, `CandidateStatus`, `CandidateStrength` in [`constants.py`](../../farmles_harvester/constants.py)

Input field contract: `DISCOVERED_LINK_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)

---

## Configuration

Recommended config values:

```json
{
  "selected_threshold": 40,
  "strong_candidate_threshold": 70,
  "write_rejected_records": true,
  "current_year": 2026
}
```

## Registry Integration

After this stage completes, the orchestrator calls `ingest_urls()` in [`orchestrator/registry_ingest.py`](../../farmles_harvester/orchestrator/registry_ingest.py). The stage itself does not touch the registry.

`ingest_urls()` reads both `02_discovered_links.jsonl` and `03_candidate_urls.jsonl`:

| Operation | What it does |
|---|---|
| `registry.upsert_many()` | Inserts or updates one row per discovered URL with `candidate_score`, `candidate_status`, `candidate_strength`, `candidate_type` from stage 03 and `source_url` from stage 02 |
| `registry.record_source()` | Records additional source mappings for URLs discovered from more than one source page |

This means `url_registry` carries forward the scoring result for every URL, allowing stage 04 to skip re-fetching candidates already known to be weak (fast mode).

---

## Definition of Done

This stage is complete when:

1. The stage reads `02_discovered_links.jsonl`.
2. The stage scores each discovered link using deterministic rules.
3. The stage assigns `candidate_score`.
4. The stage assigns `candidate_type`.
5. The stage assigns `candidate_status`.
6. The stage records `score_reasons`.
7. The stage writes `03_candidate_urls.jsonl`.
8. Unit tests cover vendor, hours, visit/location, calendar/events, about/contact, privacy, old blog, external, score clamping, candidate strength, deduplication, and malformed input.
9. The stage does not fetch pages, validate URLs, extract facts, convert markdown, call an LLM, or update the manifest directly.
