# Normalize the source leads

## Purpose
Normalizes user-supplied URLs into a consistent form without verifying reachability.
Invalid or malformed URLs are rejected and written to the errors artifact.
See [`web/url_utils.py`](../../farmles_harvester/web/url_utils.py) for the full normalization and rejection rules.

## Input Data Model
User provides a list of URLs.
- Blank lines are ignored.
- Lines starting with `#` are treated as comments.
- Each remaining line is one source lead.

## Output Data Model
For each valid source lead, one record is written to the output JSONL.

- `source_lead_id` — incrementing counter (e.g. `lead_1`); not a market_id
- `input_url` — what the user typed
- `normalized_url` — what the next stage should use
- `input_line` — line number in input, for traceability
- `normalization_status` — always `"normalized"` in the output; invalid URLs are excluded from output and written to the errors artifact instead

Duplicate normalized URLs are discarded from output; the count is recorded in the summary.

```json
{
  "run_id": "2026-05-17_132400_initial-import",
  "source_lead_id": "lead_1",
  "input_url": "apexfarmersmarket.com",
  "normalized_url": "https://apexfarmersmarket.com/",
  "input_line": 3,
  "normalization_status": "normalized",
  "normalization_notes": [],
  "normalized_at": "2026-05-17T13:24:00Z"
}
```

## Implementation

Call sequence:

1. [`stages/normalize_source_leads.py`](../../farmles_harvester/stages/normalize_source_leads.py) — `run_normalize_source_leads()` reads the seed file, writes all three artifacts, returns a `StageResult`
2. [`stages/normalize_source_leads.py`](../../farmles_harvester/stages/normalize_source_leads.py) — `parse_seed_lines()` filters blank/comment lines and deduplicates; _extend here to add new input filters_
3. [`web/url_utils.py`](../../farmles_harvester/web/url_utils.py) — `normalize_url()` applies all normalization rules
4. [`pipeline/jsonl.py`](../../farmles_harvester/pipeline/jsonl.py) — `write_jsonl()` writes output and error artifacts

Output field contract: `NORMALIZED_SOURCE_LEAD_REQUIRED` in [`models/record_contracts.py`](../../farmles_harvester/models/record_contracts.py)
