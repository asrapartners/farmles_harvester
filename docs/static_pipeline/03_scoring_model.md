# Scoring Model — Score Candidate Pages

_Scoring rules for the `score_candidate_urls` stage — see [Stage Design](03_score_candidate_links.md)._

## Quick Examples

| URL | Link text | `candidate_type` | `candidate_status` | Score |
|---|---|---|---|---|
| `/vendors` | "Vendors" | `vendor_page` | `selected` | 80 |
| `/hours` | "Market Hours" | `hours_location_page` | `selected` | 70 |
| `/events/summer-festival` | "Summer Festival" | `calendar_events_page` | `selected` | 50 |
| `/about` | "About" | `about_contact_page` | `selected` | 45 |
| `/privacy-policy` | "Privacy Policy" | `low_value_page` | `rejected` | 0 |
| `/blog/2019-opening-day` | "Opening Day 2019" | `low_value_page` | `rejected` | 0 |
| `facebook.com/pcfma` | "Facebook" | `external_reference` | `external_reference` | 0 |

These cases are exercised in the unit tests:
[`tests/unit/test_score_candidate_urls.py`](../../tests/unit/test_score_candidate_urls.py)

---

## How It Works

### `score_discovered_link()` — pure function

Each link is scored independently based solely on its URL and link text.

```
           LinkRecord
           (url, text, is_internal)
                 │
                 ▼
    ┌────────────────────────┐
    │  external link?        │──yes──► external_reference (score = 0)
    └────────────────────────┘
                 │ no
                 ▼
    ┌────────────────────────────────────────────────────┐
    │  tokenize: url path + link text → set of tokens    │
    └────────────────────────────────────────────────────┘
                 │
                 ▼
         start score = 20
                 │
                 ▼
    ┌─────────────────────────────────────────────────────┐
    │  positive signals (all matching groups stack)       │
    │  first match sets candidate_type                    │
    │                                                     │
    │  vendor           +50   → vendor_page               │
    │  hours / schedule +40   → hours_location_page       │
    │  visit / location +40   → hours_location_page       │
    │  calendar / events+40   → calendar_events_page      │
    │  about / contact  +35   → about_contact_page        │
    │  market / farmers +30   → general_market_page       │
    │  food / eat / drink+30  → general_market_page       │
    │  ebt / snap / wic +45   → general_market_page       │
    └─────────────────────────────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────────────────────┐
    │  hard reject? (privacy, login, cart, wp-admin …)   │──yes──► −60, type = low_value_page
    └────────────────────────────────────────────────────┘
                 │ no
                 ▼
    ┌────────────────────────────────────────────────────┐
    │  soft penalties (each matching term: −30)          │
    │  blog · rss · tag · recipe · video · market-match  │
    └────────────────────────────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────────────────────┐
    │  special penalties                                 │
    │  ?page=N  (N > 1)  → −60   (paginated duplicate)  │
    │  ?share=* (any)    → score = 0  (social redirect)  │
    └────────────────────────────────────────────────────┘
                 │
                 ▼
           clamp 0 … 100
                 │
                 ▼
    ┌────────────────────────────────────────────────────┐
    │  status:    hard reject → REJECTED                 │
    │             score ≥ 40  → SELECTED                 │
    │             score < 40  → REJECTED                 │
    ├────────────────────────────────────────────────────┤
    │  strength:  score ≥ 70  → strong                   │
    │             score ≥ 40  → medium                   │
    │             score < 40  → weak                     │
    └────────────────────────────────────────────────────┘
                 │
                 ▼
           CandidateScore
```

### Stage harness — 3-pass loop

After scoring every link individually, the stage makes two more passes to promote
records using context from the full set of links for the same source lead.

```
    02_discovered_links.jsonl
                 │
                 ▼
    ┌──────────────────────────────────────────────┐
    │  Pass 1 — score every link                   │
    │  score_discovered_link() per record          │
    └──────────────────────────────────────────────┘
                 │
                 ▼
    ┌──────────────────────────────────────────────┐
    │  Pass 2 — identify context signals           │
    │  • leads with meaningful sub-page selections │
    │  • leads with program-domain external links  │
    │    (fns.usda.gov, ams.usda.gov, …)           │
    └──────────────────────────────────────────────┘
                 │
                 ▼
    ┌──────────────────────────────────────────────┐
    │  Pass 3 — context-aware promotions           │
    │  • rejected internal + program link → +25    │
    │  • rejected homepage + sub-page selections   │
    │    → promote to SELECTED                     │
    └──────────────────────────────────────────────┘
                 │
                 ▼
    03_candidate_urls.jsonl
```

---

## Positive Signals

URL path and link text are tokenized together. All matching groups stack; the first match (top to bottom) sets `candidate_type`.

| Signal group | Tokens | Points | Type assigned |
|---|---|---|---|
| Vendor | `vendor` `vendors` `our-vendors` `sell` | +50 | `vendor_page` |
| Hours / schedule | `hours` `schedule` `open` | +40 | `hours_location_page` |
| Location / visit | `visit` `location` `directions` `parking` `map` | +40 | `hours_location_page` |
| Calendar / events | `calendar` `events` `opening-day` | +40 | `calendar_events_page` |
| About / contact | `about` `contact` `faq` `faqs` `mission` `history` `staff` | +35 | `about_contact_page` |
| Market / farmers | `market` `markets` `farmers-market` `certified` `farmer` `farmers` | +30 | `general_market_page` |
| Food / drink | `food` `drink` `eat` | +30 | `general_market_page` |
| EBT / nutrition programs | `ebt` `snap` `wic` `fmnp` `sfmnp` | +45 | `general_market_page` |

Baseline score for any internal link is **+20** before signals are applied.

---

## Penalties

| Penalty | Trigger | Effect |
|---|---|---|
| Hard reject | `privacy` `terms` `cookies` `login` `cart` `checkout` `wp-admin` `cdn-cgi` | −60, type = `low_value_page` |
| Soft penalty | `blog` `archive` `tag` `tags` `category` `author` `feed` `rss` `recipe` `recipes` `video` `videos` `market-match` `covid` | −30 each |
| Paginated view | `?page=N` with N > 1 | −60 |
| Social share redirect | `?share=` (any value) | score = 0, type = `low_value_page` |
| External link | `is_internal = false` | score = 0, status = `external_reference` |

Soft penalties stack — a URL matching three soft-penalty tokens loses 90 points.

Final score is clamped to **0 … 100**.

---

## Thresholds

```
selected_threshold:          40  (configurable)
strong_candidate_threshold:  70  (configurable)
```

Status and strength derivation is shown in the diagram above.

---

## Candidate Type Assignment

Type is set by the first positive signal group that matches (priority order: vendor → hours_location → calendar_events → about_contact → general_market → low_value → unknown). Hard reject and social share override type to `low_value_page` regardless.
