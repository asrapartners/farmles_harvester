import argparse
import json
from pathlib import Path

from rich.console import Console

from farmles_harvester.constants import SourceRelevanceLabel
from farmles_harvester.wiki.relevance_scorer import score_md_text, score_source

_console = Console()

_LABEL_ORDER = [
    SourceRelevanceLabel.LOW_CONFIDENCE,
    SourceRelevanceLabel.UNCERTAIN,
    SourceRelevanceLabel.LIKELY,
    SourceRelevanceLabel.CONFIRMED,
]

_LABEL_COLOR = {
    SourceRelevanceLabel.LOW_CONFIDENCE: "red",
    SourceRelevanceLabel.UNCERTAIN: "yellow",
    SourceRelevanceLabel.LIKELY: "green",
    SourceRelevanceLabel.CONFIRMED: "bright_green",
}


def _collect_sources(root: Path) -> tuple[dict[str, list[Path]], bool]:
    """Group *.md files by source.

    If root itself is a source (contains source_metadata.json), all MD files
    under it belong to one source named root.name.  Otherwise each immediate
    subdirectory of root is treated as a separate source.

    Returns (sources dict, is_single_source flag).
    """
    sources: dict[str, list[Path]] = {}
    is_single_source = (root / "source_metadata.json").exists()
    for md_file in sorted(root.rglob("*.md")):
        rel = md_file.relative_to(root)
        slug = root.name if is_single_source else rel.parts[0]
        sources.setdefault(slug, []).append(md_file)
    return sources, is_single_source


def _read_source_url(root: Path, slug: str, is_single_source: bool) -> str:
    meta_path = root / "source_metadata.json" if is_single_source else root / slug / "source_metadata.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("final_url") or meta.get("normalized_url") or ""
    except Exception:
        return ""


def _score_all(sources: dict[str, list[Path]], root: Path, is_single_source: bool) -> list[dict]:
    results = []
    total = len(sources)
    for i, (slug, paths) in enumerate(sources.items(), 1):
        _console.print(f"  [dim]({i}/{total})[/dim] {slug}", end="\r")
        texts = [p.read_text(encoding="utf-8") for p in paths]
        source_result = score_source(texts)
        file_scores = [
            {"path": str(p), **score_md_text(t)}
            for p, t in zip(paths, texts)
        ]
        label = source_result["relevance_label"]
        color = _LABEL_COLOR[label]
        _console.print(f"  [dim]({i}/{total})[/dim] {slug:<55} [{color}]{label}[/{color}]")
        results.append({
            "source_slug": slug,
            "source_url": _read_source_url(root, slug, is_single_source),
            **source_result,
            "files": file_scores,
        })
    return results


def _write_low_confidence_file(results: list[dict], output_path: Path) -> None:
    low_conf = [r for r in results if r["relevance_label"] == SourceRelevanceLabel.LOW_CONFIDENCE]
    lines = []
    for r in sorted(low_conf, key=lambda x: x["source_slug"]):
        url = r["source_url"] or r["source_slug"]
        lines.append(url)
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    _console.print(f"  Low-confidence sources written to [bold]{output_path}[/bold]  ({len(lines)} entries)")


def _print_text(results: list[dict], show_labels: set[str], root: Path, verbose: bool = False) -> None:
    total_sources = len(results)
    total_pages = sum(r["page_count"] for r in results)

    by_label: dict[str, list[dict]] = {}
    for r in results:
        by_label.setdefault(r["relevance_label"], []).append(r)

    _console.print()
    _console.print(f"── Relevance scan: [bold]{root}[/bold] ──────────────────────────────")
    _console.print(f"  Scanned [bold]{total_sources}[/bold] sources  ({total_pages} pages)")
    _console.print()
    for label in _LABEL_ORDER:
        n = len(by_label.get(label, []))
        color = _LABEL_COLOR[label]
        source_word = "source" if n == 1 else "sources"
        _console.print(f"  [{color}]{label:<20}[/{color}]  {n} {source_word}")

    for label in _LABEL_ORDER:
        group = by_label.get(label, [])
        if not group:
            continue
        if label not in show_labels:
            continue
        color = _LABEL_COLOR[label]
        note = "  ← no market content detected" if label == SourceRelevanceLabel.LOW_CONFIDENCE else ""
        _console.print()
        _console.print(f"  [{color}]{label}[/{color}]  ({len(group)} sources){note}")
        for r in sorted(group, key=lambda x: x["source_slug"]):
            pages = r["page_count"]
            hits = r["keyword_hits"]
            words = r["total_word_count"]
            _console.print(
                f"    [{color}]•[/{color}] {r['source_slug']}  "
                f"({pages} {'page' if pages == 1 else 'pages'}, "
                f"{hits} total {'hit' if hits == 1 else 'hits'}, "
                f"{words} total words)"
            )
            if verbose:
                for f in r["files"]:
                    fhits = f["keyword_hits"]
                    fwords = f["word_count"]
                    _console.print(
                        f"        [dim]{f['path']}[/dim]"
                        f"   {fhits} {'hit' if fhits == 1 else 'hits'}   {fwords} words"
                    )
    _console.print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan a folder of markdown files and report source relevance to farmer's markets"
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Root folder to scan recursively for *.md files",
    )
    parser.add_argument(
        "--label",
        choices=[*_LABEL_ORDER, "all"],
        default="low_confidence",
        help="Which confidence levels to show (default: low_confidence)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print the full path of each MD file with its individual hit and word counts",
    )
    parser.add_argument(
        "-o",
        type=Path,
        default=Path("low_confidence_src.txt"),
        metavar="OUTPUT",
        help="Output file for low-confidence source URLs (default: low_confidence_src.txt)",
    )
    args = parser.parse_args()

    root: Path = args.folder.resolve()
    if not root.exists():
        _console.print(f"[red]Folder not found: {root}[/red]")
        raise SystemExit(1)

    show_labels = set(_LABEL_ORDER) if args.label == "all" else {args.label}

    sources, is_single_source = _collect_sources(root)
    if not sources:
        _console.print(f"[yellow]No .md files found under {root}[/yellow]")
        raise SystemExit(0)

    results = _score_all(sources, root, is_single_source)

    if args.format == "json":
        output = [
            r
            for r in results
            if r["relevance_label"] in show_labels
        ]
        print(json.dumps(output, indent=2))
    else:
        _print_text(results, show_labels, root, verbose=args.verbose)

    _write_low_confidence_file(results, args.o)


if __name__ == "__main__":
    main()
