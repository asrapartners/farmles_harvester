import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

_console = Console()

_STAGE_ORDER = [
    "00_normalize_source_leads",
    "01_validate_urls",
    "02_discover_links",
    "03_score_candidate_urls",
    "04_generate_markdown_pages",
]

_STAGE_LABELS = {
    "00_normalize_source_leads": "normalize_source_leads",
    "01_validate_urls": "validate_urls",
    "02_discover_links": "discover_links",
    "03_score_candidate_urls": "score_candidate_urls",
    "04_generate_markdown_pages": "generate_markdown_pages",
}


def _parse_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _duration_s(started: str, completed: str) -> float:
    return (_parse_dt(completed) - _parse_dt(started)).total_seconds()


def _fmt_s(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


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
        dur = _fmt_s(_duration_s(stage["started_at"], stage["completed_at"]))
        one_liner = _stage_one_liner(stage_id, stage.get("counts", {}))
        status = stage.get("status", "")
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


def _print_errors(manifest: dict, run_dir: Path) -> None:
    stages = manifest.get("stages", {})
    _console.print()
    _console.print("── Errors ────────────────────────────────────────────────────")

    any_errors = False
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

        any_errors = True
        retryable = sum(1 for e in errors if e.get("retryable"))
        retryable_note = f"  ({retryable} retryable)" if retryable else ""
        _console.print(f"  [yellow]{label}  {len(errors)} errors{retryable_note}[/yellow]")

        for err in errors[:10]:
            etype = err.get("error_type", "error")
            url = err.get("source_url") or err.get("candidate_url") or err.get("discovered_url") or ""
            msg = err.get("message", "")
            if len(msg) > 80:
                msg = msg[:77] + "..."
            retryable_tag = "  [dim](retryable)[/dim]" if err.get("retryable") else ""
            url_part = f"  {url}" if url else ""
            _console.print(f"    [[dim]{etype}[/dim]]{url_part}  — {msg}{retryable_tag}")

        if len(errors) > 10:
            _console.print(f"    [dim]… and {len(errors) - 10} more[/dim]")

    if not any_errors:
        pass  # already printed "0 errors" inline
    _console.print()


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
    args = parser.parse_args()

    run_dir: Path = args.run_dir or _find_most_recent_run(args.runs_dir)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        _console.print(f"[red]No manifest.json found in {run_dir}[/red]")
        raise SystemExit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    _print_run_overview(manifest, run_dir)
    _print_stage_timings(manifest)
    _print_crawl_details(manifest)
    _print_scoring_breakdown(manifest, run_dir)
    _print_generation_details(manifest, run_dir)
    _print_errors(manifest, run_dir)


if __name__ == "__main__":
    main()
