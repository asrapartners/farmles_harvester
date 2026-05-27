import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from farmles_harvester.orchestrator.exceptions import PipelineError
from farmles_harvester.orchestrator.manifest import read_manifest
from farmles_harvester.orchestrator.run_pipeline import run_pipeline
from farmles_harvester.pipeline.stage_result import StageResult
from tests.helpers.fake_fetcher import FakeFetcher, FakeResponse

APEX_URL = "https://apex.example/"

HOMEPAGE_HTML = """\
<html><body>
<h1>Apex Farmers Market</h1>
<a href="/vendors">Vendors</a>
<a href="/visit">Visit Us</a>
<a href="/privacy-policy">Privacy Policy</a>
</body></html>
"""

VENDORS_HTML = """\
<html><body>
<h1>Vendors</h1>
<p>Smith Farm - vegetables and eggs</p>
</body></html>
"""

VISIT_HTML = """\
<html><body>
<h1>Visit Us</h1>
<p>Saturdays 8am to 12pm</p>
</body></html>
"""


def _make_fetcher() -> FakeFetcher:
    return FakeFetcher({
        APEX_URL: FakeResponse(
            url=APEX_URL, status_code=200, content_type="text/html", text=HOMEPAGE_HTML
        ),
        f"{APEX_URL}vendors": FakeResponse(
            url=f"{APEX_URL}vendors", status_code=200, content_type="text/html", text=VENDORS_HTML
        ),
        f"{APEX_URL}visit": FakeResponse(
            url=f"{APEX_URL}visit", status_code=200, content_type="text/html", text=VISIT_HTML
        ),
    })


def _make_seed(tmp_path: Path) -> Path:
    seed = tmp_path / "seed_urls.txt"
    seed.write_text(f"{APEX_URL}\n", encoding="utf-8")
    return seed


class TestRunPipeline:
    def test_creates_run_folder(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        run_dir = run_pipeline(seed, "smoke-test", runs_dir, fetcher=_make_fetcher())
        assert run_dir.exists()
        assert run_dir.is_dir()
        assert run_dir.parent == runs_dir

    def test_copies_seed_file_snapshot(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        run_dir = run_pipeline(seed, "smoke-test", runs_dir, fetcher=_make_fetcher())
        snapshot = run_dir / "seed_urls.txt"
        assert snapshot.exists()
        assert snapshot.read_text() == seed.read_text()

    def test_writes_manifest(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        run_dir = run_pipeline(seed, "smoke-test", runs_dir, fetcher=_make_fetcher())
        manifest_path = run_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert "run_id" in manifest
        assert "stages" in manifest
        assert "execution_log" in manifest

    def test_runs_stages_in_order(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        run_dir = run_pipeline(seed, "smoke-test", runs_dir, fetcher=_make_fetcher())
        manifest = read_manifest(run_dir / "manifest.json")
        stage_ids = [entry["stage_id"] for entry in manifest["execution_log"]]
        assert stage_ids == [
            "00_normalize_source_leads",
            "01_validate_urls",
            "02_discover_links",
            "03_score_candidate_urls",
            "04_generate_markdown_pages",
            "05_strip_boilerplate_blocks",
            "06_score_source_relevance",
        ]

    def test_writes_expected_artifacts(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        run_dir = run_pipeline(seed, "smoke-test", runs_dir, fetcher=_make_fetcher())
        assert (run_dir / "00_normalized_source_leads.jsonl").exists()
        assert (run_dir / "01_validated_sources.jsonl").exists()
        assert (run_dir / "02_discovered_links.jsonl").exists()
        assert (run_dir / "03_candidate_urls.jsonl").exists()
        assert (run_dir / "04_markdown_pages.jsonl").exists()
        assert (run_dir / "generated_wiki").is_dir()

    def test_manifest_records_all_stage_results(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        run_dir = run_pipeline(seed, "smoke-test", runs_dir, fetcher=_make_fetcher())
        manifest = read_manifest(run_dir / "manifest.json")
        assert set(manifest["stages"].keys()) == {
            "00_normalize_source_leads",
            "01_validate_urls",
            "02_discover_links",
            "03_score_candidate_urls",
            "04_generate_markdown_pages",
            "05_strip_boilerplate_blocks",
            "06_score_source_relevance",
        }

    def test_uses_fake_fetcher_no_real_network(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        fetcher = _make_fetcher()
        run_dir = run_pipeline(seed, "smoke-test", runs_dir, fetcher=fetcher)
        assert len(fetcher.requested_urls) > 0
        assert run_dir.exists()

    def test_generated_wiki_contains_lead_folder(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        run_dir = run_pipeline(seed, "smoke-test", runs_dir, fetcher=_make_fetcher())
        wiki_dir = run_dir / "generated_wiki"
        lead_dirs = [p for p in wiki_dir.iterdir() if p.is_dir()]
        assert len(lead_dirs) >= 1

    def test_stops_on_failed_stage(self, tmp_path):
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"

        failed_result = StageResult(
            stage_id="00_normalize_source_leads",
            stage_number="00",
            stage_name="normalize_source_leads",
            status="failed",
        )

        with patch(
            "farmles_harvester.orchestrator.run_pipeline.run_normalize_source_leads",
            return_value=failed_result,
        ):
            with pytest.raises(PipelineError) as exc_info:
                run_pipeline(seed, "smoke-test", runs_dir, fetcher=_make_fetcher())

        assert exc_info.value.stage_id == "00_normalize_source_leads"
        run_dir = exc_info.value.run_dir
        manifest = read_manifest(run_dir / "manifest.json")
        assert "00_normalize_source_leads" in manifest["stages"]
        assert manifest["stages"]["00_normalize_source_leads"]["status"] == "failed"
        assert len(manifest["execution_log"]) == 1

    def test_cli_parses_arguments_and_reports_run_folder(self, tmp_path, capsys):
        import json as _json
        seed = _make_seed(tmp_path)
        runs_dir = tmp_path / "runs"
        fake_run_dir = runs_dir / "2026-05-17_132400_smoke-test"
        fake_run_dir.mkdir(parents=True)
        (fake_run_dir / "manifest.json").write_text(_json.dumps({"stages": {}}))

        with patch(
            "farmles_harvester.cli.run_pipeline",
            return_value=fake_run_dir,
        ) as mock_run:
            from farmles_harvester.cli import main
            with patch(
                "sys.argv",
                ["farmles_harvester", "--seed-file", str(seed), "--tag", "smoke-test",
                 "--runs-dir", str(runs_dir)],
            ):
                main()

        mock_run.assert_called_once()
        captured = capsys.readouterr()
        assert "Run summary" in captured.out
