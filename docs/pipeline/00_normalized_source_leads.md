# Normalize the source leads

## Purpose
The purpose is to clean up the user supplied url's. No verification is done that the urls are valid.
use the python urllib parse to detect valid urls with the following rules
- reject spaces in hostname
- reject unsupported schemes
- reject missing hostname
- reject obvious malformed input

## Input Data Model
User provides a list of URL's.
- blank lines are ignored.
- lines starting with "#" are treated as comment.
- each remaining line is one source lead.

## Output Data Model
For each source lead produce the following record in jsonl.
The source_lead_id is an incrementing counter for the source lead in input. It is not a market_id.
The input_url is what the user typed and the normalized_url is what the next stage should use. 
If the normalized url is a duplicate then simply discard it from the output but keep a count of it in summary. The next stage should only process unique normalized leads.
The input_line is the line number in input and is used for traceability


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

