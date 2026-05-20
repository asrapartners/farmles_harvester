import json

import pytest

from farmles_harvester.models.record_contracts import DISCOVERED_LINK_REQUIRED, require_fields
from farmles_harvester.pipeline.jsonl import read_jsonl, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import StageResult
from farmles_harvester.stages.discover_links import run_discover_links
from tests.helpers.fake_fetcher import FakeFetcher, FakeResponse

RUN_ID = "2026-05-17_130000_test"

SOURCE_URL = "https://apex.example/"
SOURCE_URL_2 = "https://other.example/"

APEX_HTML = """\
<html><body>
<a href="/vendors">Vendors</a>
<a href="/visit">Visit</a>
<a href="https://facebook.com/apexmarket">Facebook</a>
<a href="mailto:info@apex.example">Email</a>
<a href="#section">Section</a>
<a href="javascript:void(0)">JS</a>
</body></html>
"""


def _validated_record(url: str, lead_id: str = "lead_1", status: str = "valid",
                      content_type: str = "text/html") -> dict:
    return {
        "run_id": RUN_ID,
        "source_lead_id": lead_id,
        "normalized_url": url,
        "final_url": url,
        "validation_status": status,
        "validated_at": "2026-05-17T13:25:00Z",
        "content_type": content_type,
    }


def _make_input(tmp_path, records: list[dict]):
    path = tmp_path / "01_validated_sources.jsonl"
    write_jsonl(path, records)
    return path


def _make_paths(tmp_path) -> StagePaths:
    return StagePaths.for_stage(tmp_path, "02", "discovered_links")


def _html_fetcher(*urls: str, html: str = APEX_HTML) -> FakeFetcher:
    return FakeFetcher({
        url: FakeResponse(url=url, status_code=200, content_type="text/html", text=html)
        for url in urls
    })


class TestRunDiscoverLinks:
    def test_writes_standard_artifacts(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()

    def test_processes_valid_and_redirected_html_records(self, tmp_path):
        records = [
            _validated_record(SOURCE_URL, lead_id="lead_1", status="valid"),
            _validated_record(SOURCE_URL_2, lead_id="lead_2", status="redirected"),
        ]
        input_path = _make_input(tmp_path, records)
        paths = _make_paths(tmp_path)
        fetcher = _html_fetcher(SOURCE_URL, SOURCE_URL_2)
        run_discover_links(input_path, paths, RUN_ID, fetcher=fetcher)
        summary = json.loads(paths.summary_path.read_text())
        assert summary["processed_sources"] == 2

    def test_skips_non_processable_records_and_counts_them(self, tmp_path):
        records = [
            _validated_record(SOURCE_URL, lead_id="lead_1", status="valid"),
            _validated_record(SOURCE_URL_2, lead_id="lead_2", status="broken"),
            {**_validated_record("https://null-ct.example/", lead_id="lead_3"), "content_type": None},
            _validated_record("https://pdf.example/", lead_id="lead_4", content_type="application/pdf"),
        ]
        input_path = _make_input(tmp_path, records)
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        summary = json.loads(paths.summary_path.read_text())
        assert summary["skipped_sources"] == 3
        assert summary["processed_sources"] == 1

    def test_fetches_final_url_not_normalized_url(self, tmp_path):
        record = {
            "run_id": RUN_ID,
            "source_lead_id": "lead_1",
            "normalized_url": "https://apex.example",
            "final_url": SOURCE_URL,
            "validation_status": "redirected",
            "validated_at": "2026-05-17T13:25:00Z",
            "content_type": "text/html",
        }
        input_path = _make_input(tmp_path, [record])
        paths = _make_paths(tmp_path)
        fetcher = _html_fetcher(SOURCE_URL)
        run_discover_links(input_path, paths, RUN_ID, fetcher=fetcher)
        assert SOURCE_URL in fetcher.requested_urls
        assert "https://apex.example" not in fetcher.requested_urls

    def test_extracts_internal_links(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        records = read_jsonl(paths.output_path)
        internal = [r for r in records if r["is_internal"]]
        assert len(internal) >= 2
        urls = [r["discovered_url"] for r in internal]
        assert any("vendors" in u for u in urls)
        assert any("visit" in u for u in urls)

    def test_extracts_external_links(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        records = read_jsonl(paths.output_path)
        external = [r for r in records if not r["is_internal"]]
        assert len(external) >= 1
        assert any("facebook.com" in r["discovered_url"] for r in external)

    def test_internal_links_follow_allowed_true(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        records = read_jsonl(paths.output_path)
        for r in records:
            if r["is_internal"]:
                assert r["follow_allowed"] is True

    def test_external_links_follow_allowed_false(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        records = read_jsonl(paths.output_path)
        for r in records:
            if not r["is_internal"]:
                assert r["follow_allowed"] is False

    def test_ignores_mailto_tel_javascript_fragment_blank(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        records = read_jsonl(paths.output_path)
        discovered = [r["discovered_url"] for r in records]
        assert not any("mailto:" in u for u in discovered)
        assert not any("javascript:" in u for u in discovered)
        assert not any(u.endswith("#section") and u == "#section" for u in discovered)

    def test_does_not_fetch_discovered_links(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        fetcher = _html_fetcher(SOURCE_URL)
        run_discover_links(input_path, paths, RUN_ID, fetcher=fetcher)
        assert fetcher.requested_urls == [SOURCE_URL]

    def test_output_records_satisfy_contract(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        records = read_jsonl(paths.output_path)
        assert len(records) > 0
        for record in records:
            require_fields(record, DISCOVERED_LINK_REQUIRED)

    def test_stage_result_is_json_serializable(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        result = run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        assert isinstance(result, StageResult)
        assert isinstance(json.dumps(result.to_dict()), str)

    def test_writes_only_to_provided_stage_paths(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = StagePaths.for_stage(tmp_path, "02", "discovered_links")
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()
