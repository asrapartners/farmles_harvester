import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console

_console = Console()

_STAGE_ORDER = [
    "00_normalize_source_leads",
    "01_validate_urls",
    "02_discover_links",
    "03_score_candidate_urls",
    "04_generate_markdown_pages",
    "05_strip_boilerplate_blocks",
    "06_score_source_relevance",
]

_STAGE_LABELS = {
    "00_normalize_source_leads": "normalize_source_leads",
    "01_validate_urls": "validate_urls",
    "02_discover_links": "discover_links",
    "03_score_candidate_urls": "score_candidate_urls",
    "04_generate_markdown_pages": "generate_markdown_pages",
    "05_strip_boilerplate_blocks": "strip_boilerplate_blocks",
    "06_score_source_relevance": "score_source_relevance",
}

_STAGE_01_FAILURE_STATUSES = {"broken", "blocked", "timeout", "fetch_error"}


def _parse_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _duration_s(started: str, completed: str) -> float:
    return (_parse_dt(completed) - _parse_dt(started)).total_seconds()


def _fmt_s(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def _stage_one_liner(stage_id: str, counts: dict) -> str:
    if stage_id == "00_normalize_source_leads":
        return f"{counts.get('output_records', 0)} seeds"
    if stage_id == "01_validate_urls":
        valid = counts.get("valid_count", 0)
        redir = counts.get("redirected_count", 0)
        broken = counts.get("broken_count", 0)
        return f"{valid + redir} valid  ({redir} redirected, {broken} broken)"
    if stage_id == "02_discover_links":
        internal = counts.get("internal_links", 0)
        external = counts.get("external_links", 0)
        return f"{internal + external} links found  ({internal} internal, {external} external)"
    if stage_id == "03_score_candidate_urls":
        sel = counts.get("selected_count", 0)
        rej = counts.get("rejected_count", 0)
        ext = counts.get("external_reference_count", 0)
        return f"{sel} selected / {rej} rejected / {ext} external"
    if stage_id == "04_generate_markdown_pages":
        written = counts.get("markdown_files_written", 0)
        failed = counts.get("pages_failed", 0)
        failed_note = f"  ({failed} failed)" if failed else ""
        return f"{written} pages written{failed_note}"
    if stage_id == "05_strip_boilerplate_blocks":
        modified = counts.get("files_modified", 0)
        removed = counts.get("total_blocks_removed", 0)
        return f"{modified} files modified  ({removed} blocks removed)"
    if stage_id == "06_score_source_relevance":
        conf = counts.get("confirmed_count", 0)
        likely = counts.get("likely_count", 0)
        unc = counts.get("uncertain_count", 0)
        low = counts.get("low_confidence_count", 0)
        return f"{conf} confirmed / {likely} likely / {unc} uncertain / {low} low-confidence"
    return ""


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _find_most_recent_run(runs_dir: Path) -> Path:
    candidates = sorted(
        (p for p in runs_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name,
    )
    if not candidates:
        raise FileNotFoundError(f"No run directories found in {runs_dir}")
    return candidates[-1]


def _print_run_overview(manifest: dict, run_dir: Path) -> None:
    run_id = manifest["run_id"]
    tag = manifest.get("tag", "")
    created_at = manifest.get("created_at", "")
    stages = manifest.get("stages", {})

    started_times = [
        _parse_dt(s["started_at"]) for s in stages.values() if "started_at" in s
    ]
    completed_times = [
        _parse_dt(s["completed_at"]) for s in stages.values() if "completed_at" in s
    ]

    total_s = None
    if started_times and completed_times:
        total_s = (max(completed_times) - min(started_times)).total_seconds()

    all_completed = all(s.get("status") == "completed" for s in stages.values())
    status_str = "[green]completed[/green]" if all_completed else "[red]incomplete / failed[/red]"

    started_display = ""
    if started_times:
        dt = min(started_times).astimezone(timezone.utc)
        started_display = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    _console.print()
    _console.print(f"── Run: [bold]{run_id}[/bold]  (tag: {tag}) ──────────────────────────")
    _console.print(f"  Seed file   : {manifest.get('seed_file_snapshot', '—')}")
    if started_display:
        _console.print(f"  Started     : {started_display}")
    if total_s is not None:
        _console.print(f"  Duration    : {_fmt_s(total_s)}")
    _console.print(f"  Status      : {status_str}")


def _print_stage_timings(manifest: dict) -> None:
    stages = manifest.get("stages", {})
    _console.print()
    _console.print("── Stage timings ─────────────────────────────────────────────")
    for stage_id in _STAGE_ORDER:
        label = _STAGE_LABELS.get(stage_id, stage_id)
        stage = stages.get(stage_id)
        if stage is None:
            _console.print(f"  [dim]{label:<32}  —[/dim]")
            continue
        status = stage.get("status", "")
        if "completed_at" not in stage:
            _console.print(f"  [yellow]{label:<32}[/yellow]  {'in-progress':>8}")
            continue
        dur = _fmt_s(_duration_s(stage["started_at"], stage["completed_at"]))
        one_liner = _stage_one_liner(stage_id, stage.get("counts", {}))
        color = "green" if status == "completed" else "red"
        _console.print(f"  [{color}]{label:<32}[/{color}]  {dur:>8}   {one_liner}")


def _print_crawl_details(manifest: dict) -> None:
    stage = manifest.get("stages", {}).get("02_discover_links")
    if not stage:
        return
    c = stage.get("counts", {})
    _console.print()
    _console.print("── Crawl  (stage 02) ─────────────────────────────────────────")
    _console.print(f"  Pages fetched   : {c.get('processed_sources', 0)}")
    _console.print(f"  Internal links  : {c.get('internal_links', 0)}")
    _console.print(f"  External links  : {c.get('external_links', 0)}")
    _console.print(f"  Max depth       : {c.get('max_depth_reached', 0)}")
    _console.print(f"  Fetch errors    : {c.get('source_fetch_errors', 0)}")


def _print_scoring_breakdown(manifest: dict, run_dir: Path) -> None:
    stage = manifest.get("stages", {}).get("03_score_candidate_urls")
    if not stage:
        return
    c = stage.get("counts", {})

    jsonl_path = run_dir / "03_candidate_urls.jsonl"
    records = _read_jsonl(jsonl_path)
    type_counts: Counter = Counter(
        r["candidate_type"]
        for r in records
        if r.get("candidate_status") == "selected"
    )

    _console.print()
    _console.print("── Scoring breakdown  (stage 03) ─────────────────────────────")
    _console.print(f"  Selected  {c.get('selected_count', 0)}")
    for ctype, n in sorted(type_counts.items(), key=lambda x: -x[1]):
        _console.print(f"    {ctype:<30} {n}")
    _console.print(f"  Rejected  {c.get('rejected_count', 0)}")
    _console.print(f"  External  {c.get('external_reference_count', 0)}")


def _print_generation_details(manifest: dict, run_dir: Path) -> None:
    stage = manifest.get("stages", {}).get("04_generate_markdown_pages")
    if not stage:
        return
    c = stage.get("counts", {})
    wiki_dir = run_dir / "generated_wiki"
    _console.print()
    _console.print("── Page generation  (stage 04) ───────────────────────────────")
    _console.print(f"  Pages written   : {c.get('markdown_files_written', 0)}")
    _console.print(f"  Pages failed    : {c.get('pages_failed', 0)}")
    _console.print(f"  Non-HTML        : {c.get('non_html_count', 0)}")
    _console.print(f"  Output folder   : {wiki_dir}")


def _print_source_relevance(manifest: dict, run_dir: Path) -> None:
    stage = manifest.get("stages", {}).get("06_score_source_relevance")
    if not stage:
        return
    c = stage.get("counts", {})

    _console.print()
    _console.print("── Source Relevance  (stage 06) ──────────────────────────────")
    label_order = ["confirmed", "likely", "uncertain", "low_confidence"]
    key_map = {
        "confirmed": "confirmed_count",
        "likely": "likely_count",
        "uncertain": "uncertain_count",
        "low_confidence": "low_confidence_count",
    }
    for label in label_order:
        n = c.get(key_map[label], 0)
        color = "red" if label == "low_confidence" else ("yellow" if label == "uncertain" else "green")
        _console.print(f"  [{color}]{label:<20}[/{color}]  {n}")


def _print_next_run_candidates(manifest: dict, run_dir: Path) -> None:
    stage = manifest.get("stages", {}).get("01_validate_urls")
    if not stage:
        return

    leads_path = run_dir / "00_normalized_source_leads.jsonl"
    validated_path = run_dir / "01_validated_sources.jsonl"
    leads = {r["source_slug"]: r.get("input_url", "") for r in _read_jsonl(leads_path)}

    failures: dict[str, list[str]] = {}
    for r in _read_jsonl(validated_path):
        status = r.get("validation_status", "")
        if status not in _STAGE_01_FAILURE_STATUSES:
            continue
        url = leads.get(r.get("source_slug", ""), r.get("normalized_url", ""))
        failures.setdefault(status, []).append(url)

    if not failures:
        return

    total = sum(len(v) for v in failures.values())
    _console.print()
    _console.print("── Next-run candidates  (stage 01 failures) ──────────────────")
    for status in sorted(failures):
        _console.print(f"  [yellow]{status:<20}[/yellow]  {len(failures[status])}")
    _console.print(f"  [bold]total[/bold]{'':16}  {total}")


def _print_errors(manifest: dict, run_dir: Path) -> None:
    stages = manifest.get("stages", {})
    _console.print()
    _console.print("── Errors ────────────────────────────────────────────────────")

    for stage_id in _STAGE_ORDER:
        stage = stages.get(stage_id)
        if not stage:
            continue
        label = _STAGE_LABELS.get(stage_id, stage_id)
        error_file = run_dir / stage.get("error_artifact", "")
        errors = _read_jsonl(error_file) if error_file.name else []

        if not errors:
            _console.print(f"  [dim]{label}  0 errors[/dim]")
            continue

        retryable = sum(1 for e in errors if e.get("retryable"))
        retryable_note = f"  ({retryable} retryable)" if retryable else ""
        _console.print(f"  [yellow]{label}  {len(errors)} errors{retryable_note}[/yellow]")
    _console.print()


_STATS_STAGE_FILES: list[tuple[str, str]] = [
    ("stage02", "02_discovered_links.jsonl"),
    ("stage03", "03_candidate_urls.jsonl"),
    ("stage04", "04_markdown_pages.jsonl"),
]


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def _build_seed_stats(run_dir: Path) -> tuple[list[dict], dict[str, int]]:
    leads = _read_jsonl(run_dir / "00_normalized_source_leads.jsonl")
    if not leads:
        return [], {}

    seed_url: dict[str, str] = {r["source_slug"]: r.get("input_url", "") for r in leads}
    order: list[str] = [r["source_slug"] for r in leads]

    validated = _read_jsonl(run_dir / "01_validated_sources.jsonl")
    lead_validated: dict[str, int] = {
        r["source_slug"]: 1
        for r in validated
        if r.get("validation_status") in _VALIDATION_SUCCESS
    }

    raw_totals: dict[str, int] = {}
    per_stage_counts: dict[str, Counter] = {}
    for col, fname in _STATS_STAGE_FILES:
        c: Counter = Counter()
        rows_seen = 0
        for r in _read_jsonl(run_dir / fname):
            rows_seen += 1
            slug = r.get("source_slug")
            if slug:
                if col == "stage04" and r.get("fetch_status") != "fetched":
                    continue
                c[slug] += 1
        per_stage_counts[col] = c
        raw_totals[col] = rows_seen

    md_bytes_by_slug: Counter = Counter()
    seen_md_paths: set[str] = set()
    for r in _read_jsonl(run_dir / "04_markdown_pages.jsonl"):
        slug = r.get("source_slug")
        if slug and r.get("fetch_status") == "fetched":
            mdp = r.get("markdown_path")
            if mdp and mdp not in seen_md_paths:
                seen_md_paths.add(mdp)
                p = run_dir / mdp
                if p.exists():
                    md_bytes_by_slug[slug] += p.stat().st_size

    stage05_by_slug: Counter = Counter()
    for r in _read_jsonl(run_dir / "05_stripped_pages.jsonl"):
        if not r.get("modified"):
            continue
        slug = r.get("source_slug", "")
        if slug:
            stage05_by_slug[slug] += 1

    stage06_by_slug: Counter = Counter()
    stage06_rows = 0
    for r in _read_jsonl(run_dir / "06_source_relevance.jsonl"):
        stage06_rows += 1
        slug = r.get("source_slug", "")
        if slug:
            stage06_by_slug[slug] += 1
    raw_totals["stage06"] = stage06_rows

    rows: list[dict] = []
    for slug in order:
        rows.append({
            "seed_url": seed_url.get(slug, ""),
            "source_slug": slug,
            "stage00": 1,
            "stage01": lead_validated.get(slug, 0),
            "stage02": per_stage_counts["stage02"].get(slug, 0),
            "stage03": per_stage_counts["stage03"].get(slug, 0),
            "stage04": per_stage_counts["stage04"].get(slug, 0),
            "stage05": stage05_by_slug.get(slug, 0),
            "stage06": stage06_by_slug.get(slug, 0),
            "md_size": md_bytes_by_slug.get(slug, 0),
        })
    return rows, raw_totals


_STATS_CSV_COLUMNS = [
    "seed_url", "source_slug",
    "stage00", "stage01", "stage02", "stage03", "stage04", "stage05", "stage06",
    "md_size",
]


def _write_stats_csv(seed_stats: list[dict], output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_STATS_CSV_COLUMNS)
        w.writeheader()
        for row in seed_stats:
            w.writerow(row)


def _print_top_seeds(seed_stats: list[dict]) -> None:
    if not seed_stats:
        return

    by_urls = sorted(
        seed_stats,
        key=lambda r: (-(r["stage02"] + r["stage03"]), r["seed_url"]),
    )
    by_urls = [r for r in by_urls if (r["stage02"] + r["stage03"]) > 0][:3]

    by_md = sorted(
        seed_stats,
        key=lambda r: (-r["md_size"], r["seed_url"]),
    )
    by_md = [r for r in by_md if r["md_size"] > 0][:3]

    if not by_urls and not by_md:
        return

    _console.print()
    _console.print("── Top seeds ─────────────────────────────────────────────────")
    if by_urls:
        _console.print("  By URLs generated (stage02 + stage03):")
        for i, r in enumerate(by_urls, 1):
            n = r["stage02"] + r["stage03"]
            _console.print(f"    {i}.  {n:>5}   {r['seed_url']}")
    if by_md:
        _console.print("  By markdown bytes:")
        for i, r in enumerate(by_md, 1):
            _console.print(f"    {i}.  {_fmt_bytes(r['md_size']):>9}   {r['seed_url']}")


def _print_reconciliation(
    seed_stats: list[dict],
    raw_totals: dict[str, int],
    manifest: dict,
    run_dir: Path,
    verify_md_bytes: bool = False,
) -> None:
    stages = manifest.get("stages", {})

    def stage_completed(stage_id: str) -> bool:
        s = stages.get(stage_id)
        return bool(s and s.get("status") == "completed")

    # (label, sum-from-per-seed-rows, authority)
    checks: list[tuple[str, int, int]] = []

    # stage01 sum vs manifest counts
    if stage_completed("01_validate_urls"):
        c = stages["01_validate_urls"].get("counts", {})
        authority = c.get("valid_count", 0) + c.get("redirected_count", 0)
        total = sum(r["stage01"] for r in seed_stats)
        checks.append(("stage01 sum", total, authority))

    # stage02 sum vs total rows seen in 02_discovered_links.jsonl
    if stage_completed("02_discover_links"):
        total = sum(r["stage02"] for r in seed_stats)
        checks.append(("stage02 sum", total, raw_totals.get("stage02", 0)))

    # stage03 sum vs total rows seen in 03_candidate_urls.jsonl
    if stage_completed("03_score_candidate_urls"):
        total = sum(r["stage03"] for r in seed_stats)
        checks.append(("stage03 sum", total, raw_totals.get("stage03", 0)))

    # stage04 sum vs manifest markdown_files_written
    if stage_completed("04_generate_markdown_pages"):
        authority = stages["04_generate_markdown_pages"].get("counts", {}).get("markdown_files_written", 0)
        total = sum(r["stage04"] for r in seed_stats)
        checks.append(("stage04 sum", total, authority))

    # stage06 sum vs total rows seen in 06_source_relevance.jsonl
    if stage_completed("06_score_source_relevance"):
        total = sum(r["stage06"] for r in seed_stats)
        checks.append(("stage06 sum", total, raw_totals.get("stage06", 0)))

    # md bytes — independent filesystem walk (catches orphan/untracked .md files).
    # Opt-in: rglob over the wiki tree is slow on networked/WSL filesystems.
    if verify_md_bytes and stage_completed("04_generate_markdown_pages"):
        wiki_sources = run_dir / "generated_wiki" / "sources"
        fs_bytes = 0
        if wiki_sources.exists():
            for p in wiki_sources.rglob("*.md"):
                fs_bytes += p.stat().st_size
        total_bytes = sum(r["md_size"] for r in seed_stats)
        checks.append(("md bytes sum", total_bytes, fs_bytes))

    skipped = [
        s for s in [
            "01_validate_urls", "02_discover_links", "03_score_candidate_urls",
            "04_generate_markdown_pages", "06_score_source_relevance",
        ]
        if not stage_completed(s)
    ]

    _console.print()
    _console.print("── Reconciliation ────────────────────────────────────────────")
    if skipped:
        labels = ", ".join(_STAGE_LABELS.get(s, s) for s in skipped)
        _console.print(f"  [dim]Skipped {len(skipped)} stages (not yet completed): {labels}[/dim]")
    for label, total, authority in checks:
        is_bytes = label.startswith("md bytes")
        fmt = _fmt_bytes if is_bytes else (lambda n: f"{n:,}")
        if total == authority:
            _console.print(f"  [green]{label:<14} ✓[/green] {fmt(total)} = {fmt(authority)}")
        else:
            delta = total - authority
            _console.print(
                f"  [yellow]{label:<14} ⚠[/yellow] {fmt(total)} ≠ {fmt(authority)}   "
                f"(delta {delta:+,})"
            )


_INVALID_SUB_KEYS = ["not_found", "forbidden", "server_error", "redirect", "timeout", "fetch_error", "non_html", "other"]

_VALIDATION_SUCCESS = {"valid", "redirected"}

_VALIDATION_TO_INVALID_SUB: dict[str, str] = {
    "broken": "not_found",
    "blocked": "forbidden",
    "timeout": "timeout",
    "fetch_error": "fetch_error",
    "invalid_url": "fetch_error",
    "non_html": "non_html",
}


def _classify_urls(manifest: dict, run_dir: Path) -> dict:
    # Step 1: build {final_url → input_url} and {final_url → validation_status} from stage 01
    final_to_input: dict[str, str] = {}
    final_to_status: dict[str, str] = {}
    for r in _read_jsonl(run_dir / "01_validated_sources.jsonl"):
        final = r.get("final_url", "")
        if final:
            final_to_input[final] = r.get("input_url", final)
            final_to_status[final] = r.get("validation_status", "")

    # Step 2: build {source_slug → relevance_label} from stage 06
    slug_label: dict[str, str] = {
        r["source_slug"]: r.get("relevance_label", "")
        for r in _read_jsonl(run_dir / "06_source_relevance.jsonl")
    }

    high_confidence = {"confirmed", "likely"}
    ok: list[str] = []
    suspect: list[str] = []
    invalid: dict[str, list[str]] = {k: [] for k in _INVALID_SUB_KEYS}
    classified_finals: set[str] = set()

    # Step 3: classify sources that made it to stage 06 via source_metadata.json
    wiki_sources_dir = run_dir / "generated_wiki" / "sources"
    if wiki_sources_dir.exists():
        for meta_path in wiki_sources_dir.glob("*/source_metadata.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            slug = meta.get("source_slug", "")
            final_url = meta.get("final_url", "")
            if not slug or not final_url:
                continue
            input_url = final_to_input.get(final_url, final_url)
            classified_finals.add(final_url)
            label = slug_label.get(slug, "")
            if label in high_confidence:
                ok.append(input_url)
            else:
                suspect.append(input_url)

    # Step 4: stage 01 failures (and successes with no wiki output) → invalid
    for r in _read_jsonl(run_dir / "01_validated_sources.jsonl"):
        final = r.get("final_url", "")
        status = r.get("validation_status", "")
        input_url = r.get("input_url", final)
        if status in _VALIDATION_SUCCESS:
            if final not in classified_finals:
                invalid["fetch_error"].append(input_url)
        else:
            sub = _VALIDATION_TO_INVALID_SUB.get(status, "other")
            invalid[sub].append(input_url)

    return {
        "run_id": manifest["run_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": sorted(ok),
        "suspect": sorted(suspect),
        "invalid": {k: sorted(v) for k, v in invalid.items()},
    }


def _print_url_status_summary(classified: dict) -> None:
    ok_n = len(classified["ok"])
    suspect_n = len(classified["suspect"])
    invalid_sub = classified["invalid"]
    invalid_n = sum(len(v) for v in invalid_sub.values())

    _console.print()
    _console.print("── URL Status Summary ────────────────────────────────────────")
    _console.print(f"  [green]ok[/green]{'':20} {ok_n}")
    _console.print(f"  [yellow]suspect[/yellow]{'':17} {suspect_n}")
    _console.print(f"  [red]invalid[/red]{'':17} {invalid_n}")
    for key in _INVALID_SUB_KEYS:
        n = len(invalid_sub.get(key, []))
        _console.print(f"  [red]  {key:<20}[/red] {n}")
    _console.print("─────────────────────────────────────────────────────────────")


def _write_url_yaml(classified: dict, output_path: Path, only: set[str] | None = None) -> None:
    data: dict = {
        "run_id": classified["run_id"],
        "generated_at": classified["generated_at"],
    }
    if only is None or "ok" in only:
        data["ok"] = classified["ok"]
    if only is None or "suspect" in only:
        data["suspect"] = classified["suspect"]
    if only is None or "invalid" in only:
        # Omit sub-keys with no URLs
        invalid_filtered = {k: v for k, v in classified["invalid"].items() if v}
        if invalid_filtered:
            data["invalid"] = invalid_filtered

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a debugging report for a farmles_harvester run"
    )
    parser.add_argument(
        "run_dir",
        nargs="?",
        type=Path,
        help="Path to a run directory (default: most recent in --runs-dir)",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        metavar="DIR",
        help="Directory containing run folders (default: runs/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("crawl_url_result.yaml"),
        metavar="FILE",
        help="Write URL status YAML to this file (default: crawl_url_result.yaml)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="CAT",
        choices=["ok", "suspect", "invalid"],
        help="Limit YAML output to these categories: ok, suspect, invalid",
    )
    parser.add_argument(
        "--stats-csv",
        type=Path,
        default=None,
        metavar="FILE",
        help="Also write per-seed-URL stage stats CSV to this file",
    )
    parser.add_argument(
        "--verify-md-bytes",
        action="store_true",
        help="Reconcile per-seed markdown bytes against a full filesystem walk "
             "(slow on networked/WSL filesystems)",
    )
    args = parser.parse_args()

    run_dir: Path = args.run_dir or _find_most_recent_run(args.runs_dir)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        _console.print(f"[red]Run not started or manifest not yet written: {run_dir}[/red]")
        raise SystemExit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    _print_run_overview(manifest, run_dir)
    _print_stage_timings(manifest)
    _print_crawl_details(manifest)
    _print_scoring_breakdown(manifest, run_dir)
    _print_generation_details(manifest, run_dir)
    _print_source_relevance(manifest, run_dir)
    _print_next_run_candidates(manifest, run_dir)
    _print_errors(manifest, run_dir)

    seed_stats, raw_totals = _build_seed_stats(run_dir)
    _print_top_seeds(seed_stats)
    _print_reconciliation(seed_stats, raw_totals, manifest, run_dir, args.verify_md_bytes)

    classified = _classify_urls(manifest, run_dir)
    _print_url_status_summary(classified)
    only_set = set(args.only) if args.only else None
    _write_url_yaml(classified, args.output, only_set)
    _console.print(f"[green]URL status written to:[/green] {args.output}")

    if args.stats_csv is not None:
        _write_stats_csv(seed_stats, args.stats_csv)
        _console.print(f"[green]Per-seed stats written to:[/green] {args.stats_csv}")


if __name__ == "__main__":
    main()
