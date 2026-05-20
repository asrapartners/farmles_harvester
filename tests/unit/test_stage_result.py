import json

from farmles_harvester.pipeline.stage_result import StageResult, STAGE_STATUS_COMPLETED


def _make_result(**kwargs) -> StageResult:
    defaults = dict(
        stage_id="00_normalize_source_leads",
        stage_number="00",
        stage_name="normalize_source_leads",
        status=STAGE_STATUS_COMPLETED,
    )
    return StageResult(**{**defaults, **kwargs})


class TestStageResult:
    def test_to_dict_returns_dict_with_required_keys(self):
        result = _make_result(counts={"output_records": 5})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["stage_id"] == "00_normalize_source_leads"
        assert d["stage_number"] == "00"
        assert d["stage_name"] == "normalize_source_leads"
        assert d["status"] == STAGE_STATUS_COMPLETED
        assert "counts" in d

    def test_to_dict_is_json_serializable(self):
        result = _make_result(counts={"output_records": 3})
        serialized = json.dumps(result.to_dict())
        assert isinstance(serialized, str)

    def test_artifact_names_are_relative_strings(self):
        result = _make_result(produced_artifacts=["00_normalized_source_leads.jsonl"])
        d = result.to_dict()
        assert d["produced_artifacts"] == ["00_normalized_source_leads.jsonl"]

    def test_default_lists_and_dicts_are_independent(self):
        r1 = _make_result()
        r2 = _make_result()
        r1.counts["output_records"] = 99
        r1.metadata["note"] = "test"
        r1.produced_artifacts.append("artifact.jsonl")
        assert "output_records" not in r2.counts
        assert "note" not in r2.metadata
        assert r2.produced_artifacts == []
