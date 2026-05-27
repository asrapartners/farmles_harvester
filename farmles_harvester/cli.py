import argparse
import json
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.status import Status

from farmles_harvester.orchestrator.exceptions import PipelineError
from farmles_harvester.orchestrator.run_pipeline import run_pipeline
from farmles_harvester.web.fetcher import HttpFetcher

_console = Console()


class _ProgressFetcher:
    def __init__(self, fetcher, on_fetch):
        self._fetcher = fetcher
        self._on_fetch = on_fetch

    def fetch(self, url: str):
        self._on_fetch(url)
        return self._fetcher.fetch(url)


def _print_run_summary(run_dir: Path) -> None:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    stages = manifest.get("stages", {})

    def counts(stage_key: str) -> dict:
        return stages.get(stage_key, {}).get("counts", {})

    c02 = counts("02_discover_links")
    c03 = counts("03_score_candidate_urls")
    c04 = counts("04_generate_markdown_pages")

    urls_crawled  = c02.get("processed_sources", 0)
    links_found   = c02.get("output_records", 0)
    internal      = c02.get("internal_links", 0)
    external      = c02.get("external_links", 0)
    max_depth     = c02.get("max_depth_reached", 0)
    selected      = c03.get("selected_count", 0)
    pages_written = c04.get("markdown_files_written", 0)
    pages_failed  = c04.get("pages_failed", 0)

    wiki_dir = run_dir / "generated_wiki"

    _console.print()
    _console.print("── Run summary ─────────────────────────────")
    _console.print(f"  Output folder  : {wiki_dir}")
    _console.print(f"  URLs crawled   : {urls_crawled}  (max depth reached: {max_depth})")
    _console.print(f"  Links found    : {links_found}  ({internal} internal, {external} external)")
    _console.print(f"  Candidates     : {selected} selected")
    failed_note = f"  ({pages_failed} failed)" if pages_failed else ""
    _console.print(f"  Pages written  : {pages_written}{failed_note}")
    _console.print("────────────────────────────────────────────")


def _resolve_category(data: dict, cat: str) -> set[str]:
    if cat == "all":
        urls: set[str] = set(data.get("ok", []))
        urls |= set(data.get("suspect", []))
        for v in data.get("invalid", {}).values():
            urls |= set(v)
        return urls
    if cat == "ok":
        return set(data.get("ok", []))
    if cat == "suspect":
        return set(data.get("suspect", []))
    if cat == "invalid":
        urls = set()
        for v in data.get("invalid", {}).values():
            urls |= set(v)
        return urls
    if cat.startswith("invalid."):
        sub = cat[len("invalid."):]
        invalid = data.get("invalid", {})
        if sub not in invalid:
            _console.print(f"[red]Unknown invalid sub-category:[/red] {sub!r}")
            _console.print(f"  Available: {', '.join(sorted(invalid.keys()))}")
            sys.exit(1)
        return set(invalid[sub])
    _console.print(f"[red]Unknown category:[/red] {cat!r}")
    _console.print("  Valid: ok  suspect  invalid  invalid.<sub>  all")
    sys.exit(1)


def _extract_urls_from_yaml(
    yaml_path: Path,
    categories: list[str],
    skip: list[str],
) -> list[str]:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    selected: set[str] = set()
    for cat in categories:
        selected |= _resolve_category(data, cat)
    for cat in skip:
        selected -= _resolve_category(data, cat)
    return sorted(selected)


def _count_all_yaml_urls(yaml_path: Path) -> int:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    total = len(data.get("ok", [])) + len(data.get("suspect", []))
    for v in data.get("invalid", {}).values():
        total += len(v)
    return total


def _print_yaml_seed_rating(
    yaml_path: Path,
    categories: list[str],
    skip: list[str],
    selected: int,
    total: int,
) -> None:
    cats_str = " ".join(categories)
    skip_str = f"  Skip       : {' '.join(skip)}" if skip else ""
    _console.print()
    _console.print("── Seed from YAML ────────────────────────────────────────────")
    _console.print(f"  File       : {yaml_path}")
    _console.print(f"  Category   : {cats_str}")
    if skip_str:
        _console.print(skip_str)
    _console.print(f"  Selected   : [bold]{selected:,}[/bold] URLs")
    _console.print(f"  Total YAML : {total:,} URLs across all categories")
    _console.print("─────────────────────────────────────────────────────────────")


def _write_temp_seed(urls: list[str], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(urls) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="farmles_harvester pipeline runner")

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--seed-file", type=Path, metavar="PATH",
                              help="Path to plain-text seed URL file")
    source_group.add_argument("--input-yaml", type=Path, metavar="PATH",
                              help="Path to crawl_url_result.yaml from report_crawl")

    parser.add_argument("--category", nargs="+", metavar="CAT",
                        help="Categories to include from --input-yaml "
                             "(ok, suspect, invalid, invalid.X, all)")
    parser.add_argument("--skip", nargs="+", metavar="CAT", default=[],
                        help="Categories to exclude (applied after --category)")
    parser.add_argument("--tag", required=True,
                        help="Human-readable label for the run")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), metavar="DIR",
                        help="Directory where run folders are created (default: runs/)")
    parser.add_argument("--max-depth", type=int, default=10, metavar="N",
                        help="Link discovery depth (default: 10)")
    parser.add_argument("--per-source-follow-cap", type=int, default=200, metavar="N",
                        help="Max URLs queued for crawling per seed source (default: 200)")
    args = parser.parse_args()

    if args.input_yaml and not args.category:
        parser.error("--category is required when using --input-yaml")

    seed_file: Path
    if args.input_yaml:
        urls = _extract_urls_from_yaml(args.input_yaml, args.category, args.skip)
        total = _count_all_yaml_urls(args.input_yaml)
        _print_yaml_seed_rating(args.input_yaml, args.category, args.skip, len(urls), total)
        cats_slug = "_".join(args.category).replace(".", "_")
        seed_file = args.runs_dir / f"_yaml_seed_{cats_slug}.txt"
        _write_temp_seed(urls, seed_file)
    else:
        seed_file = args.seed_file

    config = {
        "max_depth": args.max_depth,
        "per_source_follow_cap": args.per_source_follow_cap,
    }

    state = {"stage_label": "Starting", "fetch_count": 0}

    with Status("", console=_console, spinner="dots") as status:

        def _update_status(url: str) -> None:
            state["fetch_count"] += 1
            short_url = url if len(url) <= 70 else url[:67] + "..."
            status.update(
                f"[bold]{state['stage_label']}[/bold]  {short_url}  "
                f"[dim]\\[{state['fetch_count']} fetched][/dim]"
            )

        def _on_stage_start(stage_id: str, label: str) -> None:
            state["stage_label"] = label
            status.update(f"[bold]{label}[/bold]")

        progress_fetcher = _ProgressFetcher(HttpFetcher(), on_fetch=_update_status)

        try:
            run_dir = run_pipeline(
                seed_file=seed_file,
                tag=args.tag,
                runs_dir=args.runs_dir,
                config=config,
                fetcher=progress_fetcher,
                on_stage_start=_on_stage_start,
            )
        except PipelineError as e:
            status.stop()
            _console.print(f"[red]Run failed at stage:[/red] {e.stage_id}")
            _console.print(f"Run folder: {e.run_dir}")
            sys.exit(1)

    _print_run_summary(run_dir)


if __name__ == "__main__":
    main()
