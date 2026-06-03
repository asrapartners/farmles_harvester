# URL State Reference

The registry stores four categories of state for every URL in the `urls` table. Each category is written by a different stage and answers a distinct question about the URL. Together they determine whether a URL gets re-processed on the next run.

See [`url_registry.md`](url_registry.md) for how the pipeline reads and writes this state.

---

## Category 1 — Candidate classification (stage 03)

_What kind of page is this, and is it worth fetching?_

| Field | Values | Meaning |
|---|---|---|
| `candidate_type` | `vendor_page`, `hours_location_page`, `calendar_events_page`, `about_contact_page`, `general_market_page`, `low_value_page`, `external_reference`, `unknown` | The page category inferred from URL tokens and link text. Higher-value types score higher. |
| `candidate_status` | `selected`, `rejected`, `external_reference` | Whether this URL was chosen for fetching. `selected` means it passed the score threshold or was promoted by source-level rules. |
| `candidate_score` | integer | Raw score from the scoring model. Used to rank candidates within a source. |
| `candidate_strength` | `strong`, `medium`, `weak` | Derived bin used by fast mode. Stage 02 uses this on the next run to decide whether to re-crawl the link. |

---

## Category 2 — Fetch outcome (stage 04)

_What happened when we tried to fetch this URL?_

| Field | Values | Meaning |
|---|---|---|
| `last_outcome_class` | `ok`, `dns_error`, `tls_error`, `connect_error`, `timeout`, `http_4xx`, `http_5xx`, `rate_limited`, `redirect_loop`, `blocked`, `soft_404`, `wrong_content_type`, `empty`, `parked`, `boilerplate_only`, `size_exceeded`, `policy_rejected` | Broad outcome class. `ok` means the page was fetched and processed successfully. |
| `retry_posture` | `permanent`, `transient`, `unknown`, `NULL` | How aggressively to retry. `permanent` means never retry (e.g. NXDOMAIN, 404). `transient` means the failure may clear. `NULL` when `last_outcome_class` is `ok` or not yet attempted. |
| `outcome_detail` | free text | Optional detail to supplement `last_outcome_class` — e.g. HTTP status code or exception message. |
| `last_error_at` | ISO timestamp | When the most recent failure occurred. |
| `consecutive_failures` | integer | How many runs in a row this URL has failed. Resets to 0 on `ok`. |

Fast mode uses `retry_posture = permanent` as a hard skip gate: permanently failed URLs are never re-queued regardless of any other field.

---

## Category 3 — Render type (stage 04)

_Does this page require JavaScript to render?_

| Field | Values | Meaning |
|---|---|---|
| `render_type` | `static_html`, `dynamic_js`, `unknown` | Whether the page's content is available in the initial HTML response or requires JS execution. |
| `render_type_evidence` | free text | The signal that determined the render type — e.g. framework detected or content ratio. |
| `render_type_checked_at` | ISO timestamp | When the render type was last assessed. |

---

## Category 4 — Markdown quality (stage 04)

_How much usable content did we extract?_

| Field | Values | Meaning |
|---|---|---|
| `markdown_status` | `generated`, `empty`, `boilerplate_only`, `not_attempted` | Whether markdown was produced. `boilerplate_only` means content was fetched but stripped down to nothing after boilerplate removal. |
| `markdown_strength` | `strong`, `medium`, `weak` | Quality bin derived from `markdown_word_count`. `strong` ≥ 300 words, `medium` ≥ 100, `weak` below that. |
| `markdown_word_count` | integer | Word count of the extracted markdown. Fast mode uses this to skip re-fetching URLs that already have sufficient content. |
| `markdown_path` | relative path | Path to the `.md` file on disk, relative to the wiki sources folder. |

---

## Supporting tables

**`url_sources`** — many-to-many join between a URL and the source(s) it was discovered from. A single URL may appear under multiple sources if it was linked from more than one.

**`sources`** — one row per source domain. Holds the relevance verdict produced by stage 06.

| Field | Values | Meaning |
|---|---|---|
| `relevance_label` | `confirmed`, `likely`, `uncertain`, `low_confidence` | How confidently this source is a genuine farmers market. |
| `relevance_score` | integer | `max(0, keyword_hits × 10 − negative_hits × 5)` across all pages. |
| `keyword_hits` / `negative_hits` | integer | Raw signal counts used to derive the label. |
| `page_count` / `total_word_count` | integer | How much content was scored. |

**`meta`** — key-value store for registry-level bookkeeping (e.g. schema version).
