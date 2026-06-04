"""Integration test: detect whether a URL produces a dynamic JS-rendered page.

Runs stages 04 (generate_markdown_pages) and 05 (strip_boilerplate_blocks) against
a real URL, then checks whether the resulting content is nearly empty.

Stage 05 note: with a single URL, blocks_removed will always be 0 — stripping
requires min_files_for_fingerprint (default 3) pages from the same source. The
word count oracle therefore comes from stage 04 output.

Usage (CLI debug):
    python tests/integration/test_dynamic_detection.py <url>
    python tests/integration/test_dynamic_detection.py <url> --json
    python tests/integration/test_dynamic_detection.py <url> --weak-threshold 150

Usage (pytest):
    pytest -m integration
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest

from farmles_harvester.constants import CandidateStatus
from farmles_harvester.pipeline.jsonl import read_jsonl, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.stages.generate_markdown_pages import run_generate_markdown_pages
from farmles_harvester.stages.strip_boilerplate_blocks import run_strip_boilerplate_blocks
from farmles_harvester.web.fetcher import HttpFetcher

_DEFAULT_WEAK_THRESHOLD = 100
_DEFAULT_TIMEOUT = 15

_KNOWN_STATIC_URL = "https://apexfarmersmarket.com/"
_KNOWN_DYNAMIC_URL = "https://www.heb.com/"

_VERDICT_COLOR = {
    True:  "\033[33mDYNAMIC\033[0m",
    False: "\033[32mSTATIC\033[0m",
}


def _run_detection(url: str, timeout: int = _DEFAULT_TIMEOUT,
                   weak_threshold: int = _DEFAULT_WEAK_THRESHOLD) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ_integration")
    parsed = urlparse(url)
    source_slug = parsed.netloc.replace(".", "-").strip("-")
    source_url = f"{parsed.scheme}://{parsed.netloc}/"

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)

        input_path = run_dir / "03_candidate_urls.jsonl"
        write_jsonl(input_path, [{
            "run_id": run_id,
            "source_slug": source_slug,
            "source_url": source_url,
            "input_url": parsed.netloc,
            "normalized_url": source_url,
            "candidate_url": url,
            "candidate_type": "content_page",
            "candidate_score": 1.0,
            "candidate_status": CandidateStatus.SELECTED,
        }])

        paths_04 = StagePaths.for_stage(run_dir, "04", "markdown_pages")
        run_generate_markdown_pages(
            input_path, paths_04, run_id,
            config={},
            fetcher=HttpFetcher(timeout=timeout),
        )

        records_04 = read_jsonl(paths_04.output_path)
        r04 = records_04[0] if records_04 else {}

        paths_05 = StagePaths.for_stage(run_dir, "05", "stripped_pages")
        run_strip_boilerplate_blocks(paths_04.output_path, paths_05, run_id, config={})

        records_05 = read_jsonl(paths_05.output_path)
        r05 = records_05[0] if records_05 else {}

        word_count = r04.get("markdown_word_count", 0) or 0
        render_type = r04.get("render_type", "unknown")
        is_dynamic = render_type == "dynamic_js" or word_count < weak_threshold

        return {
            "url": url,
            "fetch_status": r04.get("fetch_status"),
            "render_type": render_type,
            "markdown_word_count": word_count,
            "markdown_strength": r04.get("markdown_strength"),
            "blocks_removed": r05.get("blocks_removed", 0),
            "modified": r05.get("modified", False),
            "is_dynamic": is_dynamic,
        }


# --- pytest integration tests ---

@pytest.mark.integration
def test_static_page():
    result = _run_detection(_KNOWN_STATIC_URL)
    assert result["fetch_status"] == "fetched", f"Fetch failed: {result}"
    assert not result["is_dynamic"], (
        f"Expected static page but got dynamic verdict: {result}"
    )
    assert result["markdown_word_count"] >= _DEFAULT_WEAK_THRESHOLD, (
        f"Word count too low for known-static URL: {result['markdown_word_count']}"
    )


@pytest.mark.integration
def test_dynamic_page():
    result = _run_detection(_KNOWN_DYNAMIC_URL)
    assert result["fetch_status"] in ("fetched", "fetch_error", "timeout"), (
        f"Unexpected fetch status: {result}"
    )
    if result["fetch_status"] == "fetched":
        assert result["is_dynamic"], (
            f"Expected dynamic page but got static verdict: {result}"
        )


# --- CLI entry point ---

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="test_dynamic_detection",
        description="Detect whether a URL produces dynamic JS-rendered content by running pipeline stages 04+05.",
    )
    parser.add_argument("url", help="URL to inspect")
    parser.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT, metavar="SEC",
                        help=f"Request timeout in seconds (default: {_DEFAULT_TIMEOUT})")
    parser.add_argument("--weak-threshold", type=int, default=_DEFAULT_WEAK_THRESHOLD, metavar="N",
                        help=f"Word count below which a page is considered dynamic (default: {_DEFAULT_WEAK_THRESHOLD})")
    parser.add_argument("--json", dest="output_json", action="store_true",
                        help="Output result as JSON")
    args = parser.parse_args()

    result = _run_detection(args.url, timeout=args.timeout, weak_threshold=args.weak_threshold)

    if args.output_json:
        print(json.dumps(result, indent=2))
        return

    use_color = sys.stdout.isatty()
    verdict_label = _VERDICT_COLOR[result["is_dynamic"]] if use_color else (
        "DYNAMIC" if result["is_dynamic"] else "STATIC"
    )

    print()
    print(f"  URL           : {result['url']}")
    print(f"  Fetch status  : {result['fetch_status']}")
    print(f"  Render type   : {result['render_type']}")
    print(f"  Word count    : {result['markdown_word_count']}")
    print(f"  Strength      : {result['markdown_strength']}")
    print(f"  Blocks removed: {result['blocks_removed']}  (0 expected — stage 05 needs 3+ files per source)")
    print(f"  Verdict       : {verdict_label}")
    print()


if __name__ == "__main__":
    main()
