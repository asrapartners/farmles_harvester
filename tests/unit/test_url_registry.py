import sqlite3

import pytest

from farmles_harvester.registry import SCHEMA_VERSION, UrlRegistry


RUN_ID = "run_test"


def _row(**overrides) -> dict:
    base = {
        "url": "https://example.com/page",
        "source_url": "https://example.com/",
        "source_lead_id": "lead_1",
        "candidate_score": 65,
        "candidate_status": "selected",
        "candidate_strength": "medium",
        "candidate_type": "vendor_page",
    }
    base.update(overrides)
    return base


class TestLifecycle:
    def test_creates_file_and_schema(self, tmp_path):
        db = tmp_path / "nested" / "registry.sqlite"
        with UrlRegistry(db) as reg:
            assert db.exists()
            assert reg.schema_version == SCHEMA_VERSION

    def test_reopen_is_idempotent(self, tmp_path):
        db = tmp_path / "registry.sqlite"
        with UrlRegistry(db) as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
        with UrlRegistry(db) as reg:
            assert reg.schema_version == SCHEMA_VERSION
            assert reg.contains("https://example.com/page")


class TestInsertPath:
    def test_insert_sets_immutable_and_mutable_fields(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            got = reg.get("https://example.com/page")
            assert got["source_url"] == "https://example.com/"
            assert got["source_lead_id"] == "lead_1"
            assert got["first_seen_at"] == "2026-01-01T00:00:00Z"
            assert got["last_seen_at"] == "2026-01-01T00:00:00Z"
            assert got["last_run_id"] == RUN_ID
            assert got["times_seen"] == 1
            assert got["source_url_count"] == 1
            assert got["render_type"] == "unknown"
            assert got["markdown_status"] == "not_attempted"
            assert got["consecutive_failures"] == 0
            assert got["last_outcome_class"] is None
            assert got["retry_posture"] is None
            assert list(reg.sources_of("https://example.com/page")) == [
                "https://example.com/"
            ]


class TestUpdatePath:
    def test_second_upsert_preserves_immutable_fields(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            reg.upsert(
                _row(candidate_score=80),
                run_id="run_2",
                now="2026-02-01T00:00:00Z",
            )
            got = reg.get("https://example.com/page")
            assert got["first_seen_at"] == "2026-01-01T00:00:00Z"
            assert got["last_seen_at"] == "2026-02-01T00:00:00Z"
            assert got["last_run_id"] == "run_2"
            assert got["times_seen"] == 2
            assert got["candidate_score"] == 80
            assert got["source_url_count"] == 1

    def test_second_seed_bumps_source_url_count(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            reg.upsert(
                _row(source_url="https://other.com/", source_lead_id="lead_2"),
                run_id=RUN_ID,
                now="2026-01-02T00:00:00Z",
            )
            got = reg.get("https://example.com/page")
            assert got["source_url_count"] == 2
            assert got["source_url"] == "https://example.com/"  # first wins
            assert got["source_lead_id"] == "lead_1"
            sources = sorted(reg.sources_of("https://example.com/page"))
            assert sources == ["https://example.com/", "https://other.com/"]

    def test_re_upsert_same_seed_does_not_bump_source_count(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-02T00:00:00Z")
            assert reg.get("https://example.com/page")["source_url_count"] == 1


class TestOutcomes:
    def test_ok_clears_posture_and_resets_failures(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            reg.record_outcome(
                "https://example.com/page",
                outcome_class="http_5xx",
                retry_posture="transient",
                detail={"status": 503},
                run_id=RUN_ID,
                now="2026-01-02T00:00:00Z",
            )
            assert reg.get("https://example.com/page")["consecutive_failures"] == 1
            reg.record_outcome(
                "https://example.com/page",
                outcome_class="http_5xx",
                retry_posture="transient",
                detail={"status": 503},
                run_id=RUN_ID,
                now="2026-01-03T00:00:00Z",
            )
            assert reg.get("https://example.com/page")["consecutive_failures"] == 2

            reg.record_outcome(
                "https://example.com/page",
                outcome_class="ok",
                retry_posture=None,
                detail=None,
                run_id=RUN_ID,
                now="2026-01-04T00:00:00Z",
            )
            got = reg.get("https://example.com/page")
            assert got["last_outcome_class"] == "ok"
            assert got["retry_posture"] is None
            assert got["consecutive_failures"] == 0
            # last_error_at preserved across recovery
            assert got["last_error_at"] == "2026-01-03T00:00:00Z"

    def test_failure_sets_error_time(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            reg.record_outcome(
                "https://example.com/page",
                outcome_class="dns_error",
                retry_posture="permanent",
                detail={"rcode": "NXDOMAIN"},
                run_id=RUN_ID,
                now="2026-01-02T00:00:00Z",
            )
            got = reg.get("https://example.com/page")
            assert got["last_outcome_class"] == "dns_error"
            assert got["retry_posture"] == "permanent"
            assert got["last_error_at"] == "2026-01-02T00:00:00Z"
            assert '"rcode":"NXDOMAIN"' in got["outcome_detail"]

    def test_rejects_invalid_class(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID)
            with pytest.raises(ValueError):
                reg.record_outcome(
                    "https://example.com/page",
                    outcome_class="not_a_class",
                    retry_posture="transient",
                    detail=None,
                    run_id=RUN_ID,
                )

    def test_rejects_ok_with_posture(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID)
            with pytest.raises(ValueError):
                reg.record_outcome(
                    "https://example.com/page",
                    outcome_class="ok",
                    retry_posture="transient",
                    detail=None,
                    run_id=RUN_ID,
                )

    def test_rejects_failure_without_posture(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID)
            with pytest.raises(ValueError):
                reg.record_outcome(
                    "https://example.com/page",
                    outcome_class="http_5xx",
                    retry_posture=None,
                    detail=None,
                    run_id=RUN_ID,
                )


class TestRenderType:
    def test_sets_render_fields_only(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            reg.set_render_type(
                "https://example.com/page",
                "dynamic_js",
                evidence={"body_length": 200, "marker_found": "next_data"},
                checked_at="2026-01-05T00:00:00Z",
            )
            got = reg.get("https://example.com/page")
            assert got["render_type"] == "dynamic_js"
            assert got["render_type_checked_at"] == "2026-01-05T00:00:00Z"
            assert '"body_length":200' in got["render_type_evidence"]
            # scoring untouched
            assert got["candidate_score"] == 65
            # bookkeeping untouched
            assert got["last_seen_at"] == "2026-01-01T00:00:00Z"

    def test_rejects_invalid_render_type(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID)
            with pytest.raises(ValueError):
                reg.set_render_type("https://example.com/page", "ssr")


class TestMarkdown:
    def test_updates_only_markdown_columns(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            reg.record_markdown_outcome(
                "https://example.com/page",
                status="generated",
                word_count=1234,
                path="sources/example-com/page.md",
                run_id=RUN_ID,
                now="2026-01-06T00:00:00Z",
            )
            got = reg.get("https://example.com/page")
            assert got["markdown_status"] == "generated"
            assert got["markdown_word_count"] == 1234
            assert got["markdown_path"] == "sources/example-com/page.md"
            assert got["candidate_score"] == 65  # unchanged

    def test_rejects_invalid_status(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID)
            with pytest.raises(ValueError):
                reg.record_markdown_outcome(
                    "https://example.com/page",
                    status="rendered",
                    run_id=RUN_ID,
                )


class TestSources:
    def test_upsert_and_get_source(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert_source(
                "https://example.com/",
                relevance_label="confirmed",
                relevance_score=305,
                keyword_hits=31,
                negative_hits=0,
                total_word_count=1842,
                page_count=4,
                run_id=RUN_ID,
                now="2026-01-01T00:00:00Z",
            )
            got = reg.get_source("https://example.com/")
            assert got["relevance_label"] == "confirmed"
            assert got["relevance_score"] == 305
            assert got["first_seen_at"] == "2026-01-01T00:00:00Z"

            reg.upsert_source(
                "https://example.com/",
                relevance_label="likely",
                relevance_score=120,
                run_id=RUN_ID,
                now="2026-02-01T00:00:00Z",
            )
            got = reg.get_source("https://example.com/")
            assert got["relevance_label"] == "likely"
            assert got["first_seen_at"] == "2026-01-01T00:00:00Z"  # immutable
            assert got["last_seen_at"] == "2026-02-01T00:00:00Z"

    def test_urls_from_returns_junction_urls(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(
                _row(url="https://example.com/a"),
                run_id=RUN_ID,
            )
            reg.upsert(
                _row(url="https://example.com/b"),
                run_id=RUN_ID,
            )
            urls = sorted(reg.urls_from("https://example.com/"))
            assert urls == ["https://example.com/a", "https://example.com/b"]


class TestBatching:
    def test_upsert_many_commits_once(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            commits = {"n": 0}

            def trace(sql):
                if sql.strip().upper().startswith("COMMIT"):
                    commits["n"] += 1

            reg._conn.set_trace_callback(trace)
            rows = [_row(url=f"https://example.com/p{i}") for i in range(50)]
            reg.upsert_many(rows, run_id=RUN_ID, now="2026-01-01T00:00:00Z")
            reg._conn.set_trace_callback(None)
            assert commits["n"] == 1
            assert reg.count() == 50


class TestQuery:
    def test_where_and_count(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            for i, score in enumerate([10, 50, 80, 95]):
                reg.upsert(
                    _row(url=f"https://example.com/p{i}", candidate_score=score),
                    run_id=RUN_ID,
                )
            strong = list(
                reg.query(where="candidate_score >= ?", params=(70,), order_by="candidate_score")
            )
            assert [r["candidate_score"] for r in strong] == [80, 95]
            assert reg.count(where="candidate_score >= ?", params=(70,)) == 2


class TestMaintenance:
    def test_rebuild_source_url_count(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID)
            # manually corrupt
            reg._conn.execute(
                "UPDATE urls SET source_url_count = 999 WHERE url = ?",
                ("https://example.com/page",),
            )
            assert reg.get("https://example.com/page")["source_url_count"] == 999
            reg.rebuild_source_url_count()
            assert reg.get("https://example.com/page")["source_url_count"] == 1


class TestCheckConstraint:
    def test_db_rejects_bad_posture_combination(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID)
            with pytest.raises(sqlite3.IntegrityError):
                reg._conn.execute(
                    "UPDATE urls SET last_outcome_class = 'ok', retry_posture = 'transient' WHERE url = ?",
                    ("https://example.com/page",),
                )


class TestDelete:
    def test_delete_removes_url_and_junction(self, tmp_path):
        with UrlRegistry(tmp_path / "r.sqlite") as reg:
            reg.upsert(_row(), run_id=RUN_ID)
            reg.delete("https://example.com/page")
            assert reg.get("https://example.com/page") is None
            assert list(reg.sources_of("https://example.com/page")) == []
