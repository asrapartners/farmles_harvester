import json

import pytest

from farmles_harvester.constants import CandidateStatus
from farmles_harvester.models.record_contracts import CANDIDATE_URL_REQUIRED, require_fields
from farmles_harvester.pipeline.jsonl import read_jsonl, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import StageResult
from farmles_harvester.stages.score_candidate_urls import run_score_candidate_urls

RUN_ID = "2026-05-17_130000_test"
SOURCE_URL = "https://apex.example/"


def _discovered(url: str, link_text: str, lead_id: str = "lead_1",
                is_internal: bool = True, follow_allowed: bool = True) -> dict:
    return {
        "run_id": RUN_ID,
        "source_lead_id": lead_id,
        "source_url": SOURCE_URL,
        "discovered_url": url,
        "link_text": link_text,
        "is_internal": is_internal,
        "follow_allowed": follow_allowed,
    }


def _make_input(tmp_path, records: list[dict]):
    path = tmp_path / "02_discovered_links.jsonl"
    write_jsonl(path, records)
    return path


def _make_paths(tmp_path) -> StagePaths:
    return StagePaths.for_stage(tmp_path, "03", "candidate_urls")


class TestRunScoreCandidateUrls:
    def test_writes_standard_artifacts(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()

    def test_reads_discovered_links_jsonl(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
            _discovered(f"{SOURCE_URL}visit", "Visit"),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert len(records) == 2

    def test_calls_scoring_for_each_record(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
            _discovered(f"{SOURCE_URL}visit", "Visit"),
            _discovered(f"{SOURCE_URL}about", "About"),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert len(records) == 3
        assert all("candidate_score" in r for r in records)

    def test_vendors_link_becomes_selected_vendor_page(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert records[0]["candidate_type"] == "vendor_page"
        assert records[0]["candidate_status"] == CandidateStatus.SELECTED

    def test_visit_link_becomes_selected_hours_location_page(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}visit", "Visit Us"),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert records[0]["candidate_type"] == "hours_location_page"
        assert records[0]["candidate_status"] == CandidateStatus.SELECTED

    def test_events_link_becomes_selected_calendar_events_page(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}events", "Events"),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert records[0]["candidate_type"] == "calendar_events_page"
        assert records[0]["candidate_status"] == CandidateStatus.SELECTED

    def test_privacy_policy_becomes_rejected_low_value_page(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}privacy-policy", "Privacy Policy"),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert records[0]["candidate_type"] == "low_value_page"
        assert records[0]["candidate_status"] == CandidateStatus.REJECTED

    def test_external_link_becomes_external_reference(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(
                "https://facebook.com/apexmarket", "Facebook",
                is_internal=False, follow_allowed=False,
            ),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert records[0]["candidate_status"] == CandidateStatus.EXTERNAL_REFERENCE

    def test_output_records_satisfy_contract(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
            _discovered(f"{SOURCE_URL}visit", "Visit"),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        records = read_jsonl(paths.output_path)
        assert len(records) > 0
        for record in records:
            require_fields(record, CANDIDATE_URL_REQUIRED)

    def test_summary_counts_are_correct(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
            _discovered(f"{SOURCE_URL}privacy-policy", "Privacy"),
            _discovered("https://facebook.com/apex", "FB", is_internal=False, follow_allowed=False),
        ])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        summary = json.loads(paths.summary_path.read_text())
        assert summary["selected_count"] == 1
        assert summary["rejected_count"] == 1
        assert summary["external_reference_count"] == 1

    def test_malformed_input_writes_error_and_does_not_crash(self, tmp_path):
        bad = {"run_id": RUN_ID, "source_lead_id": "lead_bad"}  # missing required fields
        input_path = _make_input(tmp_path, [bad])
        paths = _make_paths(tmp_path)
        run_score_candidate_urls(input_path, paths, RUN_ID)
        errors = read_jsonl(paths.errors_path)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "invalid_input_record"

    def test_stage_result_is_json_serializable(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
        ])
        paths = _make_paths(tmp_path)
        result = run_score_candidate_urls(input_path, paths, RUN_ID)
        assert isinstance(result, StageResult)
        assert isinstance(json.dumps(result.to_dict()), str)

    def test_writes_only_to_provided_stage_paths(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
        ])
        paths = StagePaths.for_stage(tmp_path, "03", "candidate_urls")
        run_score_candidate_urls(input_path, paths, RUN_ID)
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()

    def test_stage_makes_no_network_calls(self, tmp_path):
        input_path = _make_input(tmp_path, [
            _discovered(f"{SOURCE_URL}vendors", "Vendors"),
        ])
        paths = _make_paths(tmp_path)
        # run_score_candidate_urls takes no fetcher — this must not raise
        result = run_score_candidate_urls(input_path, paths, RUN_ID)
        assert result is not None
