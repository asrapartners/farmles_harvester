import argparse
import sys
from pathlib import Path

from farmles_harvester.orchestrator.exceptions import PipelineError
from farmles_harvester.orchestrator.run_pipeline import run_pipeline
from farmles_harvester.web.fetcher import HttpFetcher


def main() -> None:
    parser = argparse.ArgumentParser(description="farmles_harvester pipeline runner")
    parser.add_argument("--seed-file", required=True, type=Path, metavar="PATH",
                        help="Path to seed URL file")
    parser.add_argument("--tag", required=True,
                        help="Human-readable label for the run")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), metavar="DIR",
                        help="Directory where run folders are created (default: runs/)")
    args = parser.parse_args()

    try:
        run_dir = run_pipeline(
            seed_file=args.seed_file,
            tag=args.tag,
            runs_dir=args.runs_dir,
            fetcher=HttpFetcher(),
        )
        print(f"Run completed: {run_dir}")
    except PipelineError as e:
        print(f"Run failed at stage: {e.stage_id}")
        print(f"Run folder: {e.run_dir}")
        sys.exit(1)


if __name__ == "__main__":
    main()
