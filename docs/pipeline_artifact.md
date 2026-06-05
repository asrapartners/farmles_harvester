# Pipeline Integration Test Artifact

> Last generated: 2026-06-05 12:14 UTC
> Run ID: `2026-06-05_121414_e2e-fixture`
> Seed URL: `https://asrapartners.github.io/farmles_harvester/static/basic/`

## Stage Status

| Stage | Status |
|-------|--------|
| `00_normalize_source_leads` | ✅ completed |
| `01_validate_urls` | ✅ completed |
| `02_discover_links` | ✅ completed |
| `03_score_candidate_urls` | ✅ completed |
| `04_generate_markdown_pages` | ✅ completed |
| `05_strip_boilerplate_blocks` | ✅ completed |
| `06_score_source_relevance` | ✅ completed |
| `d01_browser_fetched_pages` | ⏭️ skipped |

## Stage 02 — Link Discovery

| Metric | Value |
|--------|-------|
| Sources processed | 1 |
| Internal links discovered | 2 |
| External links | 0 |

## Stage 04 — Markdown Generation

| Metric | Value |
|--------|-------|
| Total candidates | 2 |
| Best page URL | `https://asrapartners.github.io/farmles_harvester/static/basic/events/` |
| Best page word count | 552 |
| Best page render type | static_html |
| Best page strength | strong |

## Stage 06 — Source Relevance

| Metric | Value |
|--------|-------|
| Relevance label | **confirmed** |
| Relevance score | 980 |
| Keyword hits | 98 |
| Negative hits | 0 |
| Total word count | 1080 |
| Page count | 2 |

## Stage D01 — Dynamic Browser Fetch

| Metric | Value |
|--------|-------|
| Status | skipped |
| OK | 0 |
| Thin content | 0 |
| Failed | 0 |

## URL Registry

| Metric | Count |
|--------|-------|
| Total URLs tracked | 2 |
| Outcome OK | 2 |
| Markdown generated | 2 |
| Strength: strong | 2 |
| Strength: medium | 0 |
| Strength: weak | 0 |

### Top URLs by Word Count

| URL | Outcome | Markdown | Strength | Words |
|-----|---------|----------|----------|-------|
| `…partners.github.io/farmles_harvester/static/basic/events/` | ok | generated | strong | 552 |
| `…artners.github.io/farmles_harvester/static/basic/vendors/` | ok | generated | strong | 543 |

## Markdown Preview

Content from `https://asrapartners.github.io/farmles_harvester/static/basic/events/`:

```
Events — Greenfield Farmers Market

# Greenfield Farmers Market Events

Greenfield Farmers Market hosts a range of community events throughout the season,
from free cooking demonstrations to our beloved annual festivals. All events take place
at Greenfield Town Square unless otherwise noted. Most events are free to attend.

## Weekly Events

### Saturday Morning Cooking Demonstrations

Every Saturday at 10am, a local chef or nutritionist leads a free thirty-minute cooking
demonstration using ingredients available fresh from market vendors that morning. Past themes
have included farm-to-table summer salads, fermented foods for gut health, sheet pan roasting
for autumn vegetables, and whole-grain baking with heritage flours. Demonstrations are held
at the market demonstration kitchen near th
```
