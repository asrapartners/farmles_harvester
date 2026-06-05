"""Full end-to-end pipeline integration test against GitHub Pages static fixtures.

Runs all pipeline stages (00–06 + d01) against the static/basic fixture URL, which
links to vendors/ and events/ subpages. Verifies:
  - Every stage reached completed or skipped status
  - At least one candidate page was fetched with Greenfield farmers market content
  - The url_registry correctly reflects URL outcomes and markdown state
  - A human-readable report is written to docs/pipeline_artifact.md

Usage:
    pytest -m integration tests/integration/test_full_pipeline.py -v -s
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from farmles_harvester.orchestrator.manifest import read_manifest
from farmles_harvester.orchestrator.run_pipeline import run_pipeline
from farmles_harvester.pipeline.jsonl import read_jsonl
from farmles_harvester.registry.url_registry import UrlRegistry

_SEED_URL = "https://asrapartners.github.io/farmles_harvester/static/basic/"
_REPO_ROOT = Path(__file__).parent.parent.parent
_ARTIFACT_PATH = _REPO_ROOT / "docs" / "pipeline_artifact.md"

_REQUIRED_STAGES = [
    "00_normalize_source_leads",
    "01_validate_urls",
    "02_discover_links",
    "03_score_candidate_urls",
    "04_generate_markdown_pages",
    "05_strip_boilerplate_blocks",
    "06_score_source_relevance",
]


@pytest.mark.integration
def test_full_pipeline_static_fixture(tmp_path):
    seed = tmp_path / "seed_urls.txt"
    seed.write_text(f"{_SEED_URL}\n", encoding="utf-8")
    registry_db = tmp_path / "url_registry.db"

    run_dir = run_pipeline(
        seed_file=seed,
        tag="e2e-fixture",
        runs_dir=tmp_path / "runs",
        config={"fast_mode": False},
        registry_db=registry_db,
    )

    manifest = read_manifest(run_dir / "manifest.json")
    records_04 = read_jsonl(run_dir / "04_markdown_pages.jsonl")
    records_06 = read_jsonl(run_dir / "06_source_relevance.jsonl")

    # All static stages must complete
    for stage_id in _REQUIRED_STAGES:
        status = manifest["stages"].get(stage_id, {}).get("status")
        assert status == "completed", (
            f"Stage {stage_id} did not complete (status={status!r}):\n"
            + json.dumps(manifest["stages"].get(stage_id, {}), indent=2)
        )

    # At least one page must have been successfully fetched
    fetched = [r for r in records_04 if r.get("fetch_status") == "fetched"]
    assert fetched, (
        f"Stage 04 produced no fetched pages. Ensure the fixture subpages are "
        f"live at {_SEED_URL} (vendors/ and events/)."
    )

    # The best page (most words) must contain Greenfield content
    best = max(fetched, key=lambda r: r.get("markdown_word_count", 0))
    md_path = Path(best["markdown_path"])
    assert md_path.exists(), f"Markdown file not written: {md_path}"
    markdown = md_path.read_text(encoding="utf-8")
    word_count = len(markdown.split())

    assert word_count >= 50, (
        f"Best fetched page has only {word_count} words — content too thin.\n{markdown[:400]}"
    )
    assert "Greenfield" in markdown, (
        f"Expected 'Greenfield' in markdown from {best.get('candidate_url')}.\n"
        f"Got {word_count} words:\n{markdown[:600]}"
    )

    # Registry must reflect correct URL outcomes
    with UrlRegistry(registry_db) as reg:
        total_urls = reg.count()
        urls_ok = reg.count(where="last_outcome_class = 'ok'")
        urls_generated = reg.count(where="markdown_status = 'generated'")
        urls_strong = reg.count(where="markdown_strength = 'strong'")
        urls_medium = reg.count(where="markdown_strength = 'medium'")
        urls_weak = reg.count(where="markdown_strength = 'weak'")
        source_rec = reg.get_source(_SEED_URL)
        top_url_records = list(reg.query(
            order_by="COALESCE(markdown_word_count, 0) DESC",
            limit=10,
        ))

    assert total_urls > 0, "Registry is empty after full pipeline run"
    assert urls_ok > 0, "No URLs have outcome_class='ok' in registry"
    assert urls_generated > 0, "No URLs have markdown_status='generated' in registry"
    assert source_rec is not None, (
        f"Source {_SEED_URL!r} missing from registry sources table after stage 06"
    )

    # Collect stage-level counts for reporting
    s02 = manifest["stages"].get("02_discover_links", {}).get("counts", {})
    s04 = manifest["stages"].get("04_generate_markdown_pages", {}).get("counts", {})
    d01_status = manifest["stages"].get("d01_browser_fetched_pages", {}).get("status", "unknown")
    d01_counts = manifest["stages"].get("d01_browser_fetched_pages", {}).get("counts", {})

    relevance_label = records_06[0].get("relevance_label", "unknown") if records_06 else "unknown"
    relevance_score = records_06[0].get("relevance_score", 0) if records_06 else 0

    _print_stats(
        run_dir=run_dir,
        seed_url=_SEED_URL,
        total_04=len(records_04),
        fetched_count=len(fetched),
        best_url=best.get("candidate_url", "?"),
        best_word_count=word_count,
        total_urls=total_urls,
        urls_ok=urls_ok,
        urls_generated=urls_generated,
        urls_strong=urls_strong,
        urls_medium=urls_medium,
        urls_weak=urls_weak,
        relevance_label=relevance_label,
        relevance_score=relevance_score,
        source_rec=source_rec or {},
        s02=s02,
        d01_status=d01_status,
        d01_counts=d01_counts,
    )

    _write_artifact(
        run_dir=run_dir,
        seed_url=_SEED_URL,
        manifest=manifest,
        fetched=fetched,
        best=best,
        markdown_preview=markdown[:800],
        total_urls=total_urls,
        urls_ok=urls_ok,
        urls_generated=urls_generated,
        urls_strong=urls_strong,
        urls_medium=urls_medium,
        urls_weak=urls_weak,
        relevance_label=relevance_label,
        relevance_score=relevance_score,
        source_rec=source_rec or {},
        top_url_records=top_url_records,
        s02=s02,
        s04=s04,
        d01_status=d01_status,
        d01_counts=d01_counts,
    )
    assert _ARTIFACT_PATH.exists(), "docs/pipeline_artifact.md was not written by the test"


def _print_stats(*, run_dir, seed_url, total_04, fetched_count, best_url,
                  best_word_count, total_urls, urls_ok, urls_generated, urls_strong,
                  urls_medium, urls_weak, relevance_label, relevance_score, source_rec,
                  s02, d01_status, d01_counts):
    print()
    print("=" * 66)
    print("  Full Pipeline Integration Test — Results")
    print("=" * 66)
    print(f"  Seed URL        : {seed_url}")
    print(f"  Run directory   : {run_dir}")
    print()
    print("  Stage 02 — Link Discovery")
    print(f"    Sources processed : {s02.get('processed_sources', '?')}")
    print(f"    Internal links    : {s02.get('internal_links', '?')}")
    print(f"    External links    : {s02.get('external_links', '?')}")
    print()
    print("  Stage 04 — Markdown Generation")
    print(f"    Candidates        : {total_04}")
    print(f"    Fetched OK        : {fetched_count}")
    print(f"    Best page         : {best_url}")
    print(f"    Best word count   : {best_word_count}")
    print()
    print("  Stage 06 — Source Relevance")
    print(f"    Relevance label   : {relevance_label}")
    print(f"    Relevance score   : {relevance_score}")
    print(f"    Keyword hits      : {source_rec.get('keyword_hits', '?')}")
    print(f"    Total word count  : {source_rec.get('total_word_count', '?')}")
    print(f"    Page count        : {source_rec.get('page_count', '?')}")
    print()
    print("  Stage D01 — Dynamic Browser Fetch")
    print(f"    Status            : {d01_status}")
    if d01_status not in ("skipped", "unknown"):
        print(f"    OK                : {d01_counts.get('ok', 0)}")
        print(f"    Thin content      : {d01_counts.get('thin_content', 0)}")
        print(f"    Failed            : {d01_counts.get('failed', 0)}")
    print()
    print("  URL Registry")
    print(f"    Total URLs        : {total_urls}")
    print(f"    Outcome OK        : {urls_ok}")
    print(f"    Markdown generated: {urls_generated}")
    print(f"    Strength strong   : {urls_strong}")
    print(f"    Strength medium   : {urls_medium}")
    print(f"    Strength weak     : {urls_weak}")
    print("=" * 66)
    print()


def _write_artifact(*, run_dir, seed_url, manifest, fetched, best, markdown_preview,
                     total_urls, urls_ok, urls_generated, urls_strong, urls_medium,
                     urls_weak, relevance_label, relevance_score, source_rec,
                     top_url_records, s02, s04, d01_status, d01_counts):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    run_id = manifest.get("run_id", "unknown")

    stage_rows = []
    for stage_id, stage_data in manifest.get("stages", {}).items():
        status = stage_data.get("status", "?")
        icon = {"completed": "✅", "skipped": "⏭️"}.get(status, "❌")
        stage_rows.append(f"| `{stage_id}` | {icon} {status} |")

    url_rows = []
    for r in top_url_records:
        url = r.get("url", "")
        short_url = ("…" + url[-57:]) if len(url) > 60 else url
        outcome = r.get("last_outcome_class") or "—"
        md_status = r.get("markdown_status") or "—"
        strength = r.get("markdown_strength") or "—"
        words = r.get("markdown_word_count") or "—"
        url_rows.append(f"| `{short_url}` | {outcome} | {md_status} | {strength} | {words} |")

    content = f"""\
# Pipeline Integration Test Artifact

> Last generated: {now}
> Run ID: `{run_id}`
> Seed URL: `{seed_url}`

## Stage Status

| Stage | Status |
|-------|--------|
{chr(10).join(stage_rows)}

## Stage 02 — Link Discovery

| Metric | Value |
|--------|-------|
| Sources processed | {s02.get('processed_sources', '?')} |
| Internal links discovered | {s02.get('internal_links', '?')} |
| External links | {s02.get('external_links', '?')} |

## Stage 04 — Markdown Generation

| Metric | Value |
|--------|-------|
| Total candidates | {len(fetched)} |
| Best page URL | `{best.get('candidate_url', '?')}` |
| Best page word count | {best.get('markdown_word_count', '?')} |
| Best page render type | {best.get('render_type', '?')} |
| Best page strength | {best.get('markdown_strength', '?')} |

## Stage 06 — Source Relevance

| Metric | Value |
|--------|-------|
| Relevance label | **{relevance_label}** |
| Relevance score | {relevance_score} |
| Keyword hits | {source_rec.get('keyword_hits', '?')} |
| Negative hits | {source_rec.get('negative_hits', '?')} |
| Total word count | {source_rec.get('total_word_count', '?')} |
| Page count | {source_rec.get('page_count', '?')} |

## Stage D01 — Dynamic Browser Fetch

| Metric | Value |
|--------|-------|
| Status | {d01_status} |
| OK | {d01_counts.get('ok', 0)} |
| Thin content | {d01_counts.get('thin_content', 0)} |
| Failed | {d01_counts.get('failed', 0)} |

## URL Registry

| Metric | Count |
|--------|-------|
| Total URLs tracked | {total_urls} |
| Outcome OK | {urls_ok} |
| Markdown generated | {urls_generated} |
| Strength: strong | {urls_strong} |
| Strength: medium | {urls_medium} |
| Strength: weak | {urls_weak} |

### Top URLs by Word Count

| URL | Outcome | Markdown | Strength | Words |
|-----|---------|----------|----------|-------|
{chr(10).join(url_rows)}

## Markdown Preview

Content from `{best.get('candidate_url', '?')}`:

```
{markdown_preview}
```
"""
    _ARTIFACT_PATH.write_text(content, encoding="utf-8")
