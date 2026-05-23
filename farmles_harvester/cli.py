import argparse
import json
import sys
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(description="farmles_harvester pipeline runner")
    parser.add_argument("--seed-file", required=True, type=Path, metavar="PATH",
                        help="Path to seed URL file")
    parser.add_argument("--tag", required=True,
                        help="Human-readable label for the run")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), metavar="DIR",
                        help="Directory where run folders are created (default: runs/)")
    parser.add_argument("--max-depth", type=int, default=10, metavar="N",
                        help="Link discovery depth (default: 10; crawl stops early when no more "
                             "internal links are found — high values fetch more pages)")
    args = parser.parse_args()

    config = {"max_depth": args.max_depth}

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
                seed_file=args.seed_file,
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
