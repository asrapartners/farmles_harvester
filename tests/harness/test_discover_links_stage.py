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

    def test_depth_field_is_1_for_direct_links(self, tmp_path):
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=_html_fetcher(SOURCE_URL))
        records = read_jsonl(paths.output_path)
        assert all(r["depth"] == 1 for r in records)


class TestDepthAwareBFS:
    VENDORS_URL = f"{SOURCE_URL}vendors"
    VISIT_URL = f"{SOURCE_URL}visit"
    ABOUT_URL = f"{SOURCE_URL}about"

    def _seed_fetcher(self, internal_links: list[str], depth2_pages: dict[str, str] | None = None) -> FakeFetcher:
        link_tags = "".join(f'<a href="{u}">link</a>' for u in internal_links)
        pages = {
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=f"<html><body>{link_tags}</body></html>",
            )
        }
        for url, html in (depth2_pages or {}).items():
            pages[url] = FakeResponse(url=url, status_code=200, content_type="text/html", text=html)
        return FakeFetcher(pages)

    def test_max_depth_1_does_not_fetch_discovered_links(self, tmp_path):
        fetcher = self._seed_fetcher([self.VENDORS_URL])
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 1}, fetcher=fetcher)
        assert fetcher.requested_urls == [SOURCE_URL]

    def test_max_depth_2_fetches_internal_depth1_links(self, tmp_path):
        fetcher = self._seed_fetcher(
            [self.VENDORS_URL, self.VISIT_URL],
            depth2_pages={
                self.VENDORS_URL: "<html><body></body></html>",
                self.VISIT_URL: "<html><body></body></html>",
            },
        )
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        assert self.VENDORS_URL in fetcher.requested_urls
        assert self.VISIT_URL in fetcher.requested_urls

    def test_max_depth_2_depth2_records_carry_depth_2(self, tmp_path):
        fetcher = self._seed_fetcher(
            [self.VENDORS_URL],
            depth2_pages={
                self.VENDORS_URL: f'<html><body><a href="{self.ABOUT_URL}">About</a></body></html>',
            },
        )
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        depth2 = [r for r in records if r["depth"] == 2]
        assert len(depth2) > 0
        assert any(self.ABOUT_URL in r["discovered_url"] for r in depth2)

    def test_cycle_detection_prevents_refetching_visited_url(self, tmp_path):
        # Use a high-scoring URL (/vendors, score 70) so the score gate doesn't
        # obscure the cycle-detection behaviour being tested.
        url_b = f"{SOURCE_URL}vendors"
        fetcher = FakeFetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=f'<html><body><a href="{url_b}">Vendors</a></body></html>',
            ),
            url_b: FakeResponse(
                url=url_b, status_code=200, content_type="text/html",
                text=f'<html><body><a href="{SOURCE_URL}">Home</a></body></html>',
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 10}, fetcher=fetcher)
        assert fetcher.requested_urls.count(SOURCE_URL) == 1
        assert fetcher.requested_urls.count(url_b) == 1

    def test_source_url_is_always_the_seed_url(self, tmp_path):
        fetcher = self._seed_fetcher(
            [self.VENDORS_URL],
            depth2_pages={
                self.VENDORS_URL: f'<html><body><a href="{self.ABOUT_URL}">About</a></body></html>',
            },
        )
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert all(r["source_url"] == SOURCE_URL for r in records)

    def test_fetch_failure_at_depth2_does_not_stop_stage(self, tmp_path):
        fetcher = FakeFetcher(
            pages={
                SOURCE_URL: FakeResponse(
                    url=SOURCE_URL, status_code=200, content_type="text/html",
                    text=f'<html><body><a href="{self.VENDORS_URL}">V</a><a href="{self.VISIT_URL}">Vi</a></body></html>',
                ),
                self.VISIT_URL: FakeResponse(
                    url=self.VISIT_URL, status_code=200, content_type="text/html",
                    text="<html><body></body></html>",
                ),
            },
            exceptions={self.VENDORS_URL: RuntimeError("timeout")},
        )
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        assert self.VISIT_URL in fetcher.requested_urls

    def test_summary_includes_max_depth_reached(self, tmp_path):
        fetcher = self._seed_fetcher(
            [self.VENDORS_URL],
            depth2_pages={self.VENDORS_URL: "<html><body></body></html>"},
        )
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        summary = json.loads(paths.summary_path.read_text())
        assert summary["max_depth_reached"] == 2


class TestScoreGatedBFS:
    """
    Links discovered during BFS are scored before being enqueued.
    Low-scoring links are written to the output file but never followed.
    The threshold is configurable via config["follow_threshold"] (default 40).
    """

    # /news  → no positive signals           → score 20  (below default threshold 40)
    LOW_VALUE_URL = f"{SOURCE_URL}news"
    # /vendors → matches "vendors" keyword   → score 70  (above threshold)
    HIGH_VALUE_URL = f"{SOURCE_URL}vendors"
    # /privacy → hard-reject keyword         → score  0  (always filtered)
    HARD_REJECT_URL = f"{SOURCE_URL}privacy"
    # /about   → matches "about" keyword     → score 55  (above 40, below 60)
    MEDIUM_VALUE_URL = f"{SOURCE_URL}about"

    def _fetcher(self, pages: dict) -> FakeFetcher:
        return FakeFetcher(pages)

    def _html(self, *urls: str) -> str:
        links = "".join(f'<a href="{u}">link</a>' for u in urls)
        return f"<html><body>{links}</body></html>"

    def test_low_scoring_internal_link_is_not_fetched(self, tmp_path):
        fetcher = self._fetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=self._html(self.LOW_VALUE_URL),
            ),
            self.LOW_VALUE_URL: FakeResponse(
                url=self.LOW_VALUE_URL, status_code=200, content_type="text/html",
                text="<html><body></body></html>",
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        assert self.LOW_VALUE_URL not in fetcher.requested_urls

    def test_low_scoring_internal_link_still_appears_in_output(self, tmp_path):
        fetcher = self._fetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=self._html(self.LOW_VALUE_URL),
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert any(self.LOW_VALUE_URL in r["discovered_url"] for r in records)

    def test_high_scoring_internal_link_is_fetched(self, tmp_path):
        fetcher = self._fetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=self._html(self.HIGH_VALUE_URL),
            ),
            self.HIGH_VALUE_URL: FakeResponse(
                url=self.HIGH_VALUE_URL, status_code=200, content_type="text/html",
                text="<html><body></body></html>",
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        assert self.HIGH_VALUE_URL in fetcher.requested_urls

    def test_hard_rejected_link_is_never_fetched(self, tmp_path):
        fetcher = self._fetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=self._html(self.HARD_REJECT_URL),
            ),
            self.HARD_REJECT_URL: FakeResponse(
                url=self.HARD_REJECT_URL, status_code=200, content_type="text/html",
                text="<html><body></body></html>",
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 10}, fetcher=fetcher)
        assert self.HARD_REJECT_URL not in fetcher.requested_urls

    def test_follow_threshold_raised_prevents_following(self, tmp_path):
        # /about scores 55; raising threshold to 60 blocks it
        fetcher = self._fetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=self._html(self.MEDIUM_VALUE_URL),
            ),
            self.MEDIUM_VALUE_URL: FakeResponse(
                url=self.MEDIUM_VALUE_URL, status_code=200, content_type="text/html",
                text="<html><body></body></html>",
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(
            input_path, paths, RUN_ID,
            config={"max_depth": 2, "follow_threshold": 60},
            fetcher=fetcher,
        )
        assert self.MEDIUM_VALUE_URL not in fetcher.requested_urls

    def test_follow_threshold_default_allows_medium_scoring_link(self, tmp_path):
        # /about scores 55 ≥ default threshold 40 → should be fetched
        fetcher = self._fetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=self._html(self.MEDIUM_VALUE_URL),
            ),
            self.MEDIUM_VALUE_URL: FakeResponse(
                url=self.MEDIUM_VALUE_URL, status_code=200, content_type="text/html",
                text="<html><body></body></html>",
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        assert self.MEDIUM_VALUE_URL in fetcher.requested_urls


class TestIndexPhpDeduplication:
    CANONICAL_URL = f"{SOURCE_URL}market/downtown"
    PHP_URL = f"{SOURCE_URL}index.php/market/downtown"

    def _php_html(self) -> str:
        return (
            f'<html><body>'
            f'<a href="/market/downtown">Downtown Market</a>'
            f'<a href="/index.php/market/downtown">Downtown Market</a>'
            f'</body></html>'
        )

    def test_index_php_urls_normalized_to_canonical(self, tmp_path):
        fetcher = FakeFetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=self._php_html(),
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        discovered = [r["discovered_url"] for r in records]
        assert not any("index.php" in u for u in discovered)

    def test_index_php_dedup_prevents_canonical_url_fetched_twice(self, tmp_path):
        # At depth 2, both the canonical and index.php form score above threshold
        # (they contain "market"). After normalization both collapse to the same
        # canonical URL, so it should only be fetched once, not twice.
        canonical_html = "<html><body><p>Market info</p></body></html>"
        fetcher = FakeFetcher({
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL, status_code=200, content_type="text/html",
                text=self._php_html(),
            ),
            self.CANONICAL_URL: FakeResponse(
                url=self.CANONICAL_URL, status_code=200, content_type="text/html",
                text=canonical_html,
            ),
        })
        input_path = _make_input(tmp_path, [_validated_record(SOURCE_URL)])
        paths = _make_paths(tmp_path)
        run_discover_links(input_path, paths, RUN_ID, config={"max_depth": 2}, fetcher=fetcher)
        assert fetcher.requested_urls.count(self.CANONICAL_URL) == 1
