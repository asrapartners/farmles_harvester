import json
from pathlib import Path

from farmles_harvester.pipeline.jsonl import read_jsonl, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import StageResult
from farmles_harvester.stages.strip_boilerplate_blocks import run_strip_boilerplate_blocks

RUN_ID = "test-run-strip"
SOURCE_SLUG = "apex-example"

_SHARED_NAV = "## Main navigation\n\n* [Visit](/visit)\n* [Eat](/eat)\n* [About](/about)"
_SHARED_FOOTER = "© Test Corp. All rights reserved."


def _make_md_record(tmp_path: Path, slug: str, rel: str, content: str) -> dict:
    md_path = tmp_path / "generated_wiki" / "sources" / slug / rel
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(content, encoding="utf-8")
    return {
        "run_id": RUN_ID,
        "source_slug": slug,
        "candidate_url": f"https://{slug}.example/{rel}",
        "candidate_type": "vendor_page",
        "fetch_status": "fetched",
        "markdown_path": f"generated_wiki/sources/{slug}/{rel}",
        "markdown_filename": Path(rel).name,
"generated_at": "2026-01-01T00:00:00Z",
    }


def _make_paths(tmp_path: Path) -> StagePaths:
    return StagePaths.for_stage(tmp_path, "05", "stripped_pages")


def _three_vendor_input(tmp_path: Path) -> tuple[Path, StagePaths]:
    records = [
        _make_md_record(
            tmp_path, SOURCE_SLUG, f"vendor/farm-{name}/index.md",
            f"{_SHARED_NAV}\n\n# Farm {name.title()}\n\nSells {product}.\n\n{_SHARED_FOOTER}\n\n---\n\nSource: https://{SOURCE_SLUG}.example/vendor/farm-{name}"
        )
        for name, product in [("alpha", "apples"), ("beta", "honey"), ("gamma", "eggs")]
    ]
    # add a non-fetched record that should be ignored
    records.append({
        "run_id": RUN_ID,
        "source_slug": SOURCE_SLUG,
        "candidate_url": "https://apex-example.example/broken",
        "candidate_type": "vendor_page",
        "fetch_status": "fetch_error",
        "markdown_path": None,
        "markdown_filename": None,
        "generated_at": "2026-01-01T00:00:00Z",
    })
    input_path = tmp_path / "04_markdown_pages.jsonl"
    write_jsonl(input_path, records)
    paths = _make_paths(tmp_path)
    return input_path, paths


class TestRunStripBoilerplateBlocks:
    def test_writes_standard_artifacts(self, tmp_path):
        input_path, paths = _three_vendor_input(tmp_path)
        run_strip_boilerplate_blocks(input_path, paths, RUN_ID)
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()

    def test_shared_block_removed_from_all_files(self, tmp_path):
        input_path, paths = _three_vendor_input(tmp_path)
        run_strip_boilerplate_blocks(input_path, paths, RUN_ID)
        for name in ["alpha", "beta", "gamma"]:
            md = (tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / f"vendor/farm-{name}/index.md").read_text()
            assert "Main navigation" not in md
            assert "Test Corp" not in md

    def test_unique_content_preserved(self, tmp_path):
        input_path, paths = _three_vendor_input(tmp_path)
        run_strip_boilerplate_blocks(input_path, paths, RUN_ID)
        alpha = (tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "vendor/farm-alpha/index.md").read_text()
        beta  = (tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "vendor/farm-beta/index.md").read_text()
        gamma = (tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "vendor/farm-gamma/index.md").read_text()
        assert "Sells apples" in alpha
        assert "Sells honey" in beta
        assert "Sells eggs" in gamma

    def test_source_url_footer_preserved(self, tmp_path):
        input_path, paths = _three_vendor_input(tmp_path)
        run_strip_boilerplate_blocks(input_path, paths, RUN_ID)
        for name in ["alpha", "beta", "gamma"]:
            md = (tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / f"vendor/farm-{name}/index.md").read_text()
            assert f"Source: https://{SOURCE_SLUG}.example/vendor/farm-{name}" in md

    def test_single_source_below_min_files_unchanged(self, tmp_path):
        records = [
            _make_md_record(
                tmp_path, SOURCE_SLUG, f"vendor/farm-{name}/index.md",
                f"{_SHARED_NAV}\n\n# Farm {name.title()}\n\nContent.\n\n---\n\nSource: https://example.com/{name}"
            )
            for name in ["alpha", "beta"]
        ]
        input_path = tmp_path / "04_markdown_pages.jsonl"
        write_jsonl(input_path, records)
        paths = _make_paths(tmp_path)
        run_strip_boilerplate_blocks(input_path, paths, RUN_ID)
        md = (tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "vendor/farm-alpha/index.md").read_text()
        assert "Main navigation" in md  # NOT stripped (below min_files=3)

    def test_summary_counts_accurate(self, tmp_path):
        input_path, paths = _three_vendor_input(tmp_path)
        run_strip_boilerplate_blocks(input_path, paths, RUN_ID)
        summary = json.loads(paths.summary_path.read_text())
        assert summary["sources_processed"] == 1
        assert summary["files_modified"] == 3
        assert summary["total_blocks_removed"] > 0

    def test_output_record_per_fetched_file(self, tmp_path):
        input_path, paths = _three_vendor_input(tmp_path)
        run_strip_boilerplate_blocks(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert len(records) == 3  # one per fetched file, not the fetch_error record

    def test_stage_result_is_json_serializable(self, tmp_path):
        input_path, paths = _three_vendor_input(tmp_path)
        result = run_strip_boilerplate_blocks(input_path, paths, RUN_ID)
        assert isinstance(result, StageResult)
        assert isinstance(json.dumps(result.to_dict()), str)
