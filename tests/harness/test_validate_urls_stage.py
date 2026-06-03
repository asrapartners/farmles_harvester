import json

import pytest

from farmles_harvester.models.record_contracts import (
    VALIDATED_SOURCE_REQUIRED,
    require_fields,
)
from farmles_harvester.pipeline.jsonl import read_jsonl, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import StageResult
from farmles_harvester.stages.validate_urls import run_validate_urls
from farmles_harvester.web.fetcher import FetchTimeoutError
from tests.helpers.fake_fetcher import FakeFetcher, FakeResponse

RUN_ID = "2026-05-17_130000_test"

URL_APEX = "https://apexfarmersmarket.com/"
URL_LOCAL = "https://www.localharvest.org/"
URL_BROKEN = "https://missing.example/"
URL_BLOCKED = "https://blocked.example/"
URL_PDF = "https://pdf.example/"
URL_TIMEOUT = "https://timeout.example/"
URL_ERROR = "https://error.example/"
URL_REDIRECT = "https://redirect.example/"


def _make_input(tmp_path, records: list[dict]):
    path = tmp_path / "00_normalized_source_leads.jsonl"
    write_jsonl(path, records)
    return path


def _lead(url: str, source_slug: str = "example-com") -> dict:
    return {
        "run_id": RUN_ID,
        "source_slug": source_slug,
        "input_url": url.replace("https://", ""),
        "normalized_url": url,
        "input_line": 1,
        "normalized_at": "2026-05-17T13:24:00Z",
    }


def _make_paths(tmp_path) -> StagePaths:
    return StagePaths.for_stage(tmp_path, "01", "validated_sources")


def _html_fetcher(*urls: str) -> FakeFetcher:
    return FakeFetcher({
        url: FakeResponse(url=url, status_code=200, content_type="text/html", text="<html/>")
        for url in urls
    })


class TestRunValidateUrls:
    def test_writes_standard_artifacts(self, tmp_path):
        input_path = _make_input(tmp_path, [_lead(URL_APEX)])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=_html_fetcher(URL_APEX))
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()

    def test_200_html_becomes_valid(self, tmp_path):
        input_path = _make_input(tmp_path, [_lead(URL_APEX)])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=_html_fetcher(URL_APEX))
        records = read_jsonl(paths.output_path)
        assert len(records) == 1
        assert records[0]["validation_status"] == "valid"
        assert records[0]["http_status"] == 200
        assert records[0]["redirected"] is False

    def test_redirect_becomes_redirected(self, tmp_path):
        final = "https://www.redirect.example/"
        fetcher = FakeFetcher({
            URL_REDIRECT: FakeResponse(
                url=URL_REDIRECT,
                status_code=200,
                content_type="text/html",
                text="<html/>",
                final_url=final,
                redirect_chain=[URL_REDIRECT, final],
            )
        })
        input_path = _make_input(tmp_path, [_lead(URL_REDIRECT)])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert records[0]["validation_status"] == "redirected"
        assert records[0]["redirected"] is True
        assert len(records[0]["redirect_chain"]) >= 2

    def test_404_becomes_broken(self, tmp_path):
        fetcher = FakeFetcher({
            URL_BROKEN: FakeResponse(url=URL_BROKEN, status_code=404, content_type="text/html", text="")
        })
        input_path = _make_input(tmp_path, [_lead(URL_BROKEN)])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert records[0]["validation_status"] == "broken"
        assert records[0]["http_status"] == 404

    def test_403_becomes_blocked(self, tmp_path):
        fetcher = FakeFetcher({
            URL_BLOCKED: FakeResponse(url=URL_BLOCKED, status_code=403, content_type="text/html", text="")
        })
        input_path = _make_input(tmp_path, [_lead(URL_BLOCKED)])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert records[0]["validation_status"] == "blocked"
        assert records[0]["http_status"] == 403

    def test_200_pdf_becomes_non_html(self, tmp_path):
        fetcher = FakeFetcher({
            URL_PDF: FakeResponse(url=URL_PDF, status_code=200, content_type="application/pdf", text="")
        })
        input_path = _make_input(tmp_path, [_lead(URL_PDF)])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert records[0]["validation_status"] == "non_html"
        assert records[0]["content_type"] == "application/pdf"

    def test_timeout_becomes_timeout(self, tmp_path):
        fetcher = FakeFetcher(pages={}, exceptions={URL_TIMEOUT: FetchTimeoutError("timed out")})
        input_path = _make_input(tmp_path, [_lead(URL_TIMEOUT)])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert records[0]["validation_status"] == "timeout"
        assert "timeout" in records[0]["failure_reason"]

    def test_generic_exception_becomes_fetch_error(self, tmp_path):
        fetcher = FakeFetcher(pages={}, exceptions={URL_ERROR: RuntimeError("connection refused")})
        input_path = _make_input(tmp_path, [_lead(URL_ERROR)])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert records[0]["validation_status"] == "fetch_error"
        assert records[0]["failure_reason"] is not None

    def test_missing_normalized_url_writes_error_and_does_not_crash(self, tmp_path):
        bad_record = {
            "run_id": RUN_ID,
            "source_slug": "bad-example",
            # normalized_url intentionally omitted
            "input_url": "bad.example",
            "input_line": 1,
            "normalized_at": "2026-05-17T13:24:00Z",
        }
        input_path = _make_input(tmp_path, [bad_record])
        paths = _make_paths(tmp_path)
        run_validate_urls(input_path, paths, RUN_ID, fetcher=FakeFetcher(pages={}))
        errors = read_jsonl(paths.errors_path)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "invalid_input_record"
        summary = json.loads(paths.summary_path.read_text())
        assert summary["error_records"] == 1

    def test_output_records_satisfy_contract(self, tmp_path):
        input_path = _make_input(tmp_path, [_lead(URL_APEX), _lead(URL_LOCAL, "lead_2")])
        paths = _make_paths(tmp_path)
        run_validate_urls(
            input_path, paths, RUN_ID,
            fetcher=_html_fetcher(URL_APEX, URL_LOCAL),
        )
        records = read_jsonl(paths.output_path)
        assert len(records) > 0
        for record in records:
            require_fields(record, VALIDATED_SOURCE_REQUIRED)

    def test_stage_result_is_json_serializable(self, tmp_path):
        input_path = _make_input(tmp_path, [_lead(URL_APEX)])
        paths = _make_paths(tmp_path)
        result = run_validate_urls(input_path, paths, RUN_ID, fetcher=_html_fetcher(URL_APEX))
        assert isinstance(result, StageResult)
        serialized = json.dumps(result.to_dict())
        assert isinstance(serialized, str)

    def test_writes_only_to_provided_stage_paths(self, tmp_path):
        input_path = _make_input(tmp_path, [_lead(URL_APEX)])
        paths = StagePaths.for_stage(tmp_path, "01", "validated_sources")
        run_validate_urls(input_path, paths, RUN_ID, fetcher=_html_fetcher(URL_APEX))
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()
