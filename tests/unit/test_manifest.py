import json

import pytest

from farmles_harvester.orchestrator.manifest import (
    create_initial_manifest,
    read_manifest,
    record_stage_result,
    write_manifest,
)
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, StageResult

RUN_ID = "2026-05-17_132400_smoke-test"
CREATED_AT = "2026-05-17T13:24:00Z"


def _manifest():
    return create_initial_manifest(RUN_ID, "smoke-test", "seed_urls.txt", CREATED_AT)


def _result(stage_id="00_normalize_source_leads", stage_number="00", stage_name="normalize_source_leads"):
    return StageResult(
        stage_id=stage_id,
        stage_number=stage_number,
        stage_name=stage_name,
        status=STAGE_STATUS_COMPLETED,
        started_at="2026-05-17T13:24:00Z",
        completed_at="2026-05-17T13:24:01Z",
    )


class TestCreateInitialManifest:
    def test_returns_required_top_level_fields(self):
        m = _manifest()
        assert m["run_id"] == RUN_ID
        assert m["tag"] == "smoke-test"
        assert m["seed_file_snapshot"] == "seed_urls.txt"
        assert m["created_at"] == CREATED_AT
        assert m["stages"] == {}
        assert m["execution_log"] == []


class TestRecordStageResult:
    def test_adds_result_under_stages(self):
        m = _manifest()
        record_stage_result(m, _result())
        assert "00_normalize_source_leads" in m["stages"]

    def test_appends_entry_to_execution_log(self):
        m = _manifest()
        record_stage_result(m, _result())
        assert len(m["execution_log"]) == 1
        entry = m["execution_log"][0]
        assert entry["stage_id"] == "00_normalize_source_leads"
        assert entry["status"] == STAGE_STATUS_COMPLETED
        assert entry["sequence"] == 1

    def test_sequence_increments_across_calls(self):
        m = _manifest()
        record_stage_result(m, _result("00_normalize_source_leads", "00", "normalize_source_leads"))
        record_stage_result(m, _result("01_validate_urls", "01", "validate_urls"))
        assert m["execution_log"][0]["sequence"] == 1
        assert m["execution_log"][1]["sequence"] == 2

    def test_mutates_manifest_in_place(self):
        m = _manifest()
        result = record_stage_result(m, _result())
        assert result is None
        assert len(m["execution_log"]) == 1


class TestWriteReadManifest:
    def test_write_manifest_produces_valid_json(self, tmp_path):
        m = _manifest()
        path = tmp_path / "manifest.json"
        write_manifest(path, m)
        assert path.exists()
        parsed = json.loads(path.read_text())
        assert parsed["run_id"] == RUN_ID

    def test_read_manifest_round_trips(self, tmp_path):
        m = _manifest()
        path = tmp_path / "manifest.json"
        write_manifest(path, m)
        loaded = read_manifest(path)
        assert loaded == m
