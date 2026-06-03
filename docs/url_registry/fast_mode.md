# Fast Mode

Fast mode makes the harvester skip URLs that are already well-understood from a prior run. Instead of re-crawling and re-fetching everything, each run only does real work on URLs that are **new**, **improved**, or **retryable**.

Enabled by setting `fast_mode: true` in config **and** passing a populated registry into `run_pipeline()`. Without a registry the flag has no effect.

---

## Where it applies

Fast mode is checked in two stages: `discover_links` (stage 02) and `generate_markdown_pages` (stage 04). Both stages receive the registry as an optional kwarg and gate work behind an `EvalVerdict`.

---

## Stage 02 — discover_links: should we follow this link?

During BFS crawl, every internal link that scores above `follow_threshold` is a candidate for further crawling. In fast mode, before adding it to the queue, the stage calls:

```python
registry.get(discovered_url)          # single row lookup
evaluate_url_strength(row, min_strength=fast_url_min_strength, ...)
```

**`evaluate_url_strength` decision table:**

| Registry row | `should_process` | Reason |
|---|---|---|
| `None` (never seen) | ✅ yes | new |
| `retry_posture = permanent` | ❌ no | permanent failure |
| `candidate_strength >= min_strength` | ✅ yes | strong enough to re-crawl |
| `candidate_strength < min_strength` | ❌ no | below threshold |

Config knobs:
- `fast_url_min_strength` (default: `"strong"`) — minimum `candidate_strength` to allow re-crawl
- `fast_skip_permanent_failures` (default: `true`) — whether permanent failures are skipped

URLs skipped here are counted as `fast_skipped` in the stage summary but still appear in the output JSONL (they were discovered, just not followed deeper).

---

## Stage 04 — generate_markdown_pages: should we re-fetch this candidate?

After deduplication and candidate selection, in fast mode the stage bulk-fetches all selected URLs from the registry in one call:

```python
registry.get_many([r["candidate_url"] for r in selected_records])
evaluate_markdown_strength(row, min_word_count=fast_md_min_words, ...)
```

**`evaluate_markdown_strength` decision table:**

| Registry row | `should_process` | Reason |
|---|---|---|
| `None` (never seen) | ✅ yes | new |
| `retry_posture = permanent` | ❌ no | permanent failure |
| `markdown_word_count >= min_word_count` | ❌ no | already has sufficient content |
| `markdown_word_count < min_word_count` | ✅ yes | thin/empty — worth retrying |

Config knobs:
- `fast_md_min_words` (default: `150`) — word count threshold above which re-fetch is skipped
- `fast_skip_permanent_failures` (default: `true`) — whether permanent failures are skipped

URLs skipped here are counted as `fast_skipped` in the stage summary and no HTTP request is made for them.

---

## What "high confidence" means

The term means different things in each stage — there is no single signal.

**Stage 02 — crawl confidence = scoring strength**
A URL is considered high confidence if its `candidate_strength` from the prior run's scoring stage is at or above `fast_url_min_strength` (default `"strong"`). Strength ranks as `weak < medium < strong`. A strong URL was already well-scored and does not need to be re-crawled; a weak or medium one may benefit from another pass.

**Stage 04 — fetch confidence = content volume**
A URL is considered high confidence if its `markdown_word_count` from the prior run is at or above `fast_md_min_words` (default `150`). A URL that already produced substantial markdown does not need to be re-fetched; one that produced thin or empty content is worth retrying.

**Shared hard gate — permanent failure**
Regardless of strength or word count, any URL with `retry_posture = permanent` is always skipped in both stages. This covers cases like NXDOMAIN seed URLs recorded by `ingest_validation_failures`.

**New URLs are always processed**
A URL with no registry entry (`row is None`) bypasses all confidence checks and is processed unconditionally.

---

## Staleness and how to reset

Registry state is persistent but not self-correcting. Two classes of stale entries can cause URLs to be skipped indefinitely:

**URL-level staleness** — a URL that was weak or permanently failed in a prior run keeps those classifications forever. A site that was unreachable during run 1 gets `retry_posture = permanent` and is never retried, even if it recovers.

**Source-level staleness** — a source domain scored `low_confidence` by stage 06 blocks every URL from that domain on all future runs. A thin first crawl (too few pages, boilerplate-heavy content) can permanently misclassify a genuine farmers market.

**The fix: run with `fast_mode: false`**

Disabling fast mode bypasses all registry reads in both stages. Every URL is re-crawled and re-fetched from scratch regardless of stored `candidate_strength`, `retry_posture`, or source `relevance_label`. The registry is still written to at the end of each stage, so a clean run rebuilds the state from current observations.

```
fast_mode: false   →  no registry reads  →  full re-crawl
fast_mode: true    →  registry reads active  →  skips apply
```

Run with fast mode off periodically, or whenever you suspect the registry has drifted from reality.

---

## Example

Run 1 (no registry / fast_mode off):
- All discovered URLs are crawled and fetched from scratch
- Registry is populated with outcomes, strengths, and word counts

Run 2 (fast_mode on, same registry):
- `discover_links` skips internal links already known as `strong` — only new links or weaker ones get re-queued
- `generate_markdown_pages` skips candidates that already produced ≥ 150 words of markdown
- URLs with `retry_posture: permanent` (e.g. NXDOMAIN seed URLs recorded by `ingest_validation_failures`) are skipped in both stages
