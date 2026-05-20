from pathlib import Path

from farmles_harvester.pipeline.stage_paths import StagePaths


class TestStagePaths:
    def test_creates_expected_filenames(self, tmp_path):
        paths = StagePaths.for_stage(tmp_path / "run", "00", "normalized_source_leads")
        assert paths.output_path.name == "00_normalized_source_leads.jsonl"
        assert paths.summary_path.name == "00_normalized_source_leads_summary.json"
        assert paths.errors_path.name == "00_normalized_source_leads_errors.jsonl"

    def test_paths_are_absolute(self, tmp_path):
        run_dir = Path("relative/run")
        paths = StagePaths.for_stage(run_dir, "00", "normalized_source_leads")
        assert paths.output_path.is_absolute()
        assert paths.summary_path.is_absolute()
        assert paths.errors_path.is_absolute()

    def test_different_stage_creates_different_filenames(self, tmp_path):
        paths = StagePaths.for_stage(tmp_path / "run", "01", "validated_sources")
        assert paths.output_path.name == "01_validated_sources.jsonl"
        assert paths.summary_path.name == "01_validated_sources_summary.json"
        assert paths.errors_path.name == "01_validated_sources_errors.jsonl"
