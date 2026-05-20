import json

import pytest

from farmles_harvester.pipeline.jsonl import read_jsonl, write_json, write_jsonl


class TestWriteReadRoundTrip:
    def test_round_trip(self, tmp_path):
        records = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
        path = tmp_path / "out.jsonl"
        write_jsonl(path, records)
        assert read_jsonl(path) == records

    def test_read_skips_blank_lines(self, tmp_path):
        path = tmp_path / "out.jsonl"
        path.write_text('{"id": 1}\n\n{"id": 2}\n\n', encoding="utf-8")
        records = read_jsonl(path)
        assert records == [{"id": 1}, {"id": 2}]

    def test_write_creates_parent_directory(self, tmp_path):
        path = tmp_path / "nested" / "deep" / "out.jsonl"
        write_jsonl(path, [{"x": 1}])
        assert path.exists()
        assert read_jsonl(path) == [{"x": 1}]

    def test_read_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"id": 1}\nnot json\n', encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            read_jsonl(path)


class TestWriteJson:
    def test_write_json_round_trip(self, tmp_path):
        path = tmp_path / "summary.json"
        obj = {"count": 5, "status": "completed"}
        write_json(path, obj)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == obj

    def test_write_json_creates_parent_directory(self, tmp_path):
        path = tmp_path / "nested" / "summary.json"
        write_json(path, {"ok": True})
        assert path.exists()
