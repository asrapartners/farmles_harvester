"""Standalone utility: detect whether a URL serves static or JS-rendered HTML.

Usage:
    detect_render <url>
    detect_render <url> --verbose
    detect_render <url> --timeout 30
"""
import argparse
import json
import sys

from farmles_harvester.web.fetcher import FetchTimeoutError, HttpFetcher
from farmles_harvester.web.render_type_detector import detect_render_type

_RENDER_TYPE_COLOR = {
    "static_html": "\033[32m",   # green
    "dynamic_js":  "\033[33m",   # yellow
    "unknown":     "\033[90m",   # grey
}
_RESET = "\033[0m"


def _colored(text: str, render_type: str) -> str:
    if not sys.stdout.isatty():
        return text
    color = _RENDER_TYPE_COLOR.get(render_type, "")
    return f"{color}{text}{_RESET}"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="detect_render",
        description="Detect whether a URL serves static HTML or a JS-rendered SPA shell.",
    )
    parser.add_argument("url", help="URL to inspect")
    parser.add_argument(
        "--timeout", type=int, default=15, metavar="SEC",
        help="Request timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print full evidence dict",
    )
    parser.add_argument(
        "--json", dest="output_json", action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    fetcher = HttpFetcher(timeout=args.timeout)

    try:
        response = fetcher.fetch(args.url)
    except FetchTimeoutError:
        print(f"error: request timed out after {args.timeout}s", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if response.status_code != 200:
        print(f"error: HTTP {response.status_code} from {args.url}", file=sys.stderr)
        sys.exit(1)

    ct = response.content_type.lower()
    if not (ct.startswith("text/html") or ct.startswith("application/xhtml")):
        print(f"error: non-HTML content-type: {response.content_type!r}", file=sys.stderr)
        sys.exit(1)

    render_type, evidence = detect_render_type(response.text)
    final_url = response.final_url or args.url

    if args.output_json:
        print(json.dumps({
            "url": args.url,
            "final_url": final_url,
            "render_type": render_type,
            "evidence": evidence,
        }, indent=2))
        return

    label = _colored(render_type, render_type)
    print(f"\n  URL         : {final_url}")
    print(f"  Render type : {label}")
    if args.verbose or render_type != "static_html":
        print(f"  Evidence    : {evidence}")
    print()


if __name__ == "__main__":
    main()
