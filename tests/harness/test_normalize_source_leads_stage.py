import json

import pytest

from farmles_harvester.pipeline.jsonl import read_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import StageResult
from farmles_harvester.stages.normalize_source_leads import run_normalize_source_leads

RUN_ID = "2026-05-17_130000_test"

SEED_TEXT = """\
# NC markets

apexfarmersmarket.com
https://apexfarmersmarket.com/
https://www.localharvest.org/farmers-markets?utm_source=test
"""


def _make_seed(tmp_path, text: str):
    seed = tmp_path / "seed_urls.txt"
    seed.write_text(text, encoding="utf-8")
    return seed


def _make_paths(tmp_path) -> StagePaths:
    return StagePaths.for_stage(tmp_path, "00", "normalized_source_leads")


class TestRunNormalizeSourceLeads:
    def test_writes_output_jsonl(self, tmp_path):
        seed = _make_seed(tmp_path, SEED_TEXT)
        paths = _make_paths(tmp_path)
        run_normalize_source_leads(seed, paths, RUN_ID)
        assert paths.output_path.exists()
        records = read_jsonl(paths.output_path)
        assert len(records) == 2  # apex + localharvest (apex dupe deduplicated)

    def test_output_record_has_required_fields(self, tmp_path):
        seed = _make_seed(tmp_path, SEED_TEXT)
        paths = _make_paths(tmp_path)
        run_normalize_source_leads(seed, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        for rec in records:
            assert "run_id" in rec
            assert "source_lead_id" in rec
            assert "normalized_url" in rec
            assert "normalized_at" in rec
            assert "input_line" in rec
            assert rec["run_id"] == RUN_ID

    def test_skips_blank_and_comment_lines(self, tmp_path):
        text = "# comment\n\nhttps://example.com\n"
        seed = _make_seed(tmp_path, text)
        paths = _make_paths(tmp_path)
        run_normalize_source_leads(seed, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert len(records) == 1
        assert records[0]["normalized_url"] == "https://example.com/"

    def test_deduplicates_normalized_urls(self, tmp_path):
        text = "apexfarmersmarket.com\nhttps://apexfarmersmarket.com/\n"
        seed = _make_seed(tmp_path, text)
        paths = _make_paths(tmp_path)
        run_normalize_source_leads(seed, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert len(records) == 1

    def test_writes_summary_json(self, tmp_path):
        seed = _make_seed(tmp_path, SEED_TEXT)
        paths = _make_paths(tmp_path)
        run_normalize_source_leads(seed, paths, RUN_ID)
        assert paths.summary_path.exists()
        summary = json.loads(paths.summary_path.read_text())
        assert isinstance(summary, dict)

    def test_summary_has_correct_counts(self, tmp_path):
        text = "# comment\n\napexfarmersmarket.com\nhttps://apexfarmersmarket.com/\nhttps://other.com\n"
        seed = _make_seed(tmp_path, text)
        paths = _make_paths(tmp_path)
        run_normalize_source_leads(seed, paths, RUN_ID)
        summary = json.loads(paths.summary_path.read_text())
        assert summary["blank_lines"] == 1
        assert summary["comment_lines"] == 1
        assert summary["output_records"] == 2
        assert summary["duplicate_count"] == 1

    def test_writes_errors_jsonl_when_empty(self, tmp_path):
        seed = _make_seed(tmp_path, SEED_TEXT)
        paths = _make_paths(tmp_path)
        run_normalize_source_leads(seed, paths, RUN_ID)
        assert paths.errors_path.exists()
        errors = read_jsonl(paths.errors_path)
        assert errors == []

    def test_writes_error_record_for_invalid_url(self, tmp_path):
        text = "https://valid.com\nnot a url at all\n"
        seed = _make_seed(tmp_path, text)
        paths = _make_paths(tmp_path)
        run_normalize_source_leads(seed, paths, RUN_ID)
        errors = read_jsonl(paths.errors_path)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "invalid_url"
        assert errors[0]["run_id"] == RUN_ID
        assert "input_url" in errors[0]

    def test_returns_stage_result(self, tmp_path):
        seed = _make_seed(tmp_path, SEED_TEXT)
        paths = _make_paths(tmp_path)
        result = run_normalize_source_leads(seed, paths, RUN_ID)
        assert isinstance(result, StageResult)

    def test_stage_result_serializable(self, tmp_path):
        seed = _make_seed(tmp_path, SEED_TEXT)
        paths = _make_paths(tmp_path)
        result = run_normalize_source_leads(seed, paths, RUN_ID)
        serialized = json.dumps(result.to_dict())
        assert isinstance(serialized, str)

    def test_stage_result_consumed_and_produced_artifacts(self, tmp_path):
        seed = _make_seed(tmp_path, SEED_TEXT)
        paths = _make_paths(tmp_path)
        result = run_normalize_source_leads(seed, paths, RUN_ID)
        assert "seed_urls.txt" in result.consumed_artifacts
        assert paths.output_path.name in result.produced_artifacts

    def test_output_files_at_stage_paths_locations(self, tmp_path):
        seed = _make_seed(tmp_path, SEED_TEXT)
        paths = StagePaths.for_stage(tmp_path, "00", "normalized_source_leads")
        run_normalize_source_leads(seed, paths, RUN_ID)
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()
