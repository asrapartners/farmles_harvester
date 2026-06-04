import json
from pathlib import Path

import pytest

from farmles_harvester.orchestrator.run_dynamic_pipeline import run_dynamic_pipeline
from farmles_harvester.pipeline.jsonl import read_jsonl, write_jsonl
from farmles_harvester.pipeline.stage_result import STAGE_STATUS_COMPLETED, STAGE_STATUS_SKIPPED
from farmles_harvester.registry.url_registry import UrlRegistry

RUN_ID = "2026-05-17_130000_test"
SOURCE_SLUG = "greenfield-farmers-market"
SOURCE_URL_A = "https://greenfield.example/"
SOURCE_URL_B = "https://greenfield.example/vendors"


class FakeCrawl4AIFetcher:
    def __init__(self, ok_results: list[dict], error_records: list[dict]):
        self._ok = ok_results
        self._errors = error_records
        self.called_with: list[dict] | None = None

    def fetch_batch(self, records: list[dict]) -> tuple[list[dict], list[dict]]:
        self.called_with = records
        return self._ok, self._errors


def _candidate(url: str, md_path: str) -> dict:
    return {
        "candidate_url": url,
        "source_slug": SOURCE_SLUG,
        "markdown_path": md_path,
        "render_type": "dynamic_js",
    }


def _ok_result(url: str, md_path: str, word_count: int = 200, overwritten: bool = False) -> dict:
    return {
        "candidate_url": url,
        "source_slug": SOURCE_SLUG,
        "markdown_path": md_path,
        "word_count": word_count,
        "overwritten": overwritten,
        "bytes_before": 50 if overwritten else 0,
        "bytes_after": word_count * 6,
        "bytes_incr_pcnt": 100.0 if not overwritten else 50.0,
        "fetch_status": "ok",
    }


def _error_result(url: str) -> dict:
    return {"candidate_url": url, "error": "TimeoutError"}


@pytest.fixture()
def registry(tmp_path):
    reg = UrlRegistry(tmp_path / "registry.db")
    yield reg
    reg.close()


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------

def test_two_ok_results_written_and_registry_updated(tmp_path, registry):
    md_a = str(tmp_path / "wiki/source/a/index.md")
    md_b = str(tmp_path / "wiki/source/b/index.md")
    input_path = tmp_path / "dynamic_candidates.jsonl"
    write_jsonl(input_path, [
        _candidate(SOURCE_URL_A, md_a),
        _candidate(SOURCE_URL_B, md_b),
    ])

    fake = FakeCrawl4AIFetcher(
        ok_results=[_ok_result(SOURCE_URL_A, md_a), _ok_result(SOURCE_URL_B, md_b)],
        error_records=[],
    )

    result = run_dynamic_pipeline(
        input_path=input_path,
        run_dir=tmp_path,
        registry=registry,
        run_id=RUN_ID,
        fetcher=fake,
    )

    assert result.status == STAGE_STATUS_COMPLETED
    assert result.counts["ok"] == 2
    assert result.counts["failed"] == 0

    records = read_jsonl(tmp_path / "d01_browser_fetched_pages.jsonl")
    assert len(records) == 2
    assert all(r["fetch_status"] == "ok" for r in records)

    errors = read_jsonl(tmp_path / "d01_browser_fetched_pages_errors.jsonl")
    assert errors == []

    summary = json.loads((tmp_path / "d01_browser_fetched_pages_summary.json").read_text())
    assert summary["total"] == 2
    assert summary["ok"] == 2
    assert summary["failed"] == 0


def test_mixed_results_split_to_correct_files(tmp_path, registry):
    md_a = str(tmp_path / "wiki/source/a/index.md")
    input_path = tmp_path / "dynamic_candidates.jsonl"
    write_jsonl(input_path, [
        _candidate(SOURCE_URL_A, md_a),
        _candidate(SOURCE_URL_B, ""),
    ])

    fake = FakeCrawl4AIFetcher(
        ok_results=[_ok_result(SOURCE_URL_A, md_a)],
        error_records=[_error_result(SOURCE_URL_B)],
    )

    result = run_dynamic_pipeline(
        input_path=input_path,
        run_dir=tmp_path,
        registry=registry,
        run_id=RUN_ID,
        fetcher=fake,
    )

    assert result.status == STAGE_STATUS_COMPLETED
    assert result.counts["ok"] == 1
    assert result.counts["failed"] == 1

    assert len(read_jsonl(tmp_path / "d01_browser_fetched_pages.jsonl")) == 1
    errors = read_jsonl(tmp_path / "d01_browser_fetched_pages_errors.jsonl")
    assert len(errors) == 1
    assert errors[0]["candidate_url"] == SOURCE_URL_B


def test_overwrite_count_in_summary(tmp_path, registry):
    md_a = str(tmp_path / "wiki/source/a/index.md")
    md_b = str(tmp_path / "wiki/source/b/index.md")
    input_path = tmp_path / "dynamic_candidates.jsonl"
    write_jsonl(input_path, [
        _candidate(SOURCE_URL_A, md_a),
        _candidate(SOURCE_URL_B, md_b),
    ])

    fake = FakeCrawl4AIFetcher(
        ok_results=[
            _ok_result(SOURCE_URL_A, md_a, overwritten=True),
            _ok_result(SOURCE_URL_B, md_b, overwritten=False),
        ],
        error_records=[],
    )

    run_dynamic_pipeline(
        input_path=input_path,
        run_dir=tmp_path,
        registry=registry,
        run_id=RUN_ID,
        fetcher=fake,
    )

    summary = json.loads((tmp_path / "d01_browser_fetched_pages_summary.json").read_text())
    assert summary["overwritten_count"] == 1


# ---------------------------------------------------------------------------
# empty / skip
# ---------------------------------------------------------------------------

def test_empty_candidates_returns_skipped(tmp_path, registry):
    input_path = tmp_path / "dynamic_candidates.jsonl"
    write_jsonl(input_path, [])

    result = run_dynamic_pipeline(
        input_path=input_path,
        run_dir=tmp_path,
        registry=registry,
        run_id=RUN_ID,
    )

    assert result.status == STAGE_STATUS_SKIPPED
    assert not (tmp_path / "d01_browser_fetched_pages.jsonl").exists()


def test_missing_input_file_returns_skipped(tmp_path, registry):
    result = run_dynamic_pipeline(
        input_path=tmp_path / "nonexistent.jsonl",
        run_dir=tmp_path,
        registry=registry,
        run_id=RUN_ID,
    )
    assert result.status == STAGE_STATUS_SKIPPED
