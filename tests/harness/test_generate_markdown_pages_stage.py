import json

import pytest

from farmles_harvester.constants import CandidateStatus
from farmles_harvester.models.record_contracts import MARKDOWN_PAGE_REQUIRED, require_fields
from farmles_harvester.pipeline.jsonl import read_jsonl, write_jsonl
from farmles_harvester.pipeline.stage_paths import StagePaths
from farmles_harvester.pipeline.stage_result import StageResult
from farmles_harvester.stages.generate_markdown_pages import run_generate_markdown_pages
from farmles_harvester.web.fetcher import FetchTimeoutError
from tests.helpers.fake_fetcher import FakeFetcher, FakeResponse

RUN_ID = "2026-05-17_130000_test"
SOURCE_URL = "https://apex.example/"
SOURCE_SLUG = "apex-example"
VENDORS_URL = f"{SOURCE_URL}vendors"
VISIT_URL = f"{SOURCE_URL}visit"

VENDOR_HTML = """\
<html><body>
<h1>Vendors</h1>
<ul>
  <li>Smith Farm - vegetables and eggs</li>
</ul>
</body></html>
"""

_FORBIDDEN_META_KEYS = {"generated_at", "run_id", "harvester_run_id", "source_lead_id", "timestamp", "content_hash"}


def _candidate(url: str, candidate_type: str, lead_id: str = "lead_1",
               status: str = CandidateStatus.SELECTED, score: int = 80) -> dict:
    return {
        "run_id": RUN_ID,
        "source_lead_id": lead_id,
        "source_url": SOURCE_URL,
        "candidate_url": url,
        "candidate_type": candidate_type,
        "candidate_score": score,
        "candidate_status": status,
    }


def _make_input(tmp_path, records: list[dict]):
    path = tmp_path / "03_candidate_urls.jsonl"
    write_jsonl(path, records)
    return path


def _make_paths(tmp_path) -> StagePaths:
    return StagePaths.for_stage(tmp_path, "04", "markdown_pages")


def _html_fetcher(**url_html: str) -> FakeFetcher:
    return FakeFetcher({
        url: FakeResponse(url=url, status_code=200, content_type="text/html", text=html)
        for url, html in url_html.items()
    })


class TestRunGenerateMarkdownPages:
    def test_writes_standard_artifacts(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()

    def test_processes_only_selected_candidates(self, tmp_path):
        records = [
            _candidate(VENDORS_URL, "vendor_page", status=CandidateStatus.SELECTED),
            _candidate(VISIT_URL, "hours_location_page", status=CandidateStatus.REJECTED),
            _candidate("https://fb.com/apex", "external_reference",
                       status=CandidateStatus.EXTERNAL_REFERENCE),
        ]
        input_path = _make_input(tmp_path, records)
        paths = _make_paths(tmp_path)
        fetcher = _html_fetcher(**{VENDORS_URL: VENDOR_HTML})
        run_generate_markdown_pages(input_path, paths, RUN_ID, fetcher=fetcher)
        assert fetcher.requested_urls == [VENDORS_URL]
        summary = json.loads(paths.summary_path.read_text())
        assert summary["selected_candidates"] == 1
        assert summary["skipped_candidates"] == 2

    def test_writes_markdown_mirroring_url_path(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        md_file = tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "vendors" / "index.md"
        assert md_file.exists()

    def test_pages_directory_is_not_created(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        pages_dir = tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "pages"
        assert not pages_dir.exists()

    def test_root_url_writes_index_md_at_source_root(self, tmp_path):
        root_html = "<html><body><h1>Home</h1></body></html>"
        input_path = _make_input(tmp_path, [_candidate(SOURCE_URL, "general_market_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{SOURCE_URL: root_html}))
        md_file = tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "index.md"
        assert md_file.exists()

    def test_writes_stable_source_metadata_json(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        meta_path = tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "source_metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert set(meta.keys()) == {"source_slug", "input_url", "normalized_url", "final_url"}
        assert meta["source_slug"] == SOURCE_SLUG
        assert meta["final_url"] == SOURCE_URL
        assert not _FORBIDDEN_META_KEYS & set(meta.keys())

    def test_html_is_converted_to_markdown(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        md_file = tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG / "vendors" / "index.md"
        content = md_file.read_text()
        assert "Vendors" in content
        assert "Smith Farm - vegetables and eggs" in content
        assert f"Source: {VENDORS_URL}" in content

    def test_output_records_satisfy_contract(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        records = read_jsonl(paths.output_path)
        assert len(records) > 0
        for record in records:
            require_fields(record, MARKDOWN_PAGE_REQUIRED)

    def test_output_records_include_source_slug(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        records = read_jsonl(paths.output_path)
        for record in records:
            assert record["source_slug"] == SOURCE_SLUG

    def test_two_different_urls_write_to_separate_paths(self, tmp_path):
        our_vendors_url = f"{SOURCE_URL}our-vendors"
        records = [
            _candidate(VENDORS_URL, "vendor_page", lead_id="lead_1"),
            _candidate(our_vendors_url, "vendor_page", lead_id="lead_1"),
        ]
        input_path = _make_input(tmp_path, records)
        paths = _make_paths(tmp_path)
        fetcher = FakeFetcher({
            VENDORS_URL: FakeResponse(url=VENDORS_URL, status_code=200,
                                      content_type="text/html", text="<p>Vendors 1</p>"),
            our_vendors_url: FakeResponse(url=our_vendors_url, status_code=200,
                                          content_type="text/html", text="<p>Vendors 2</p>"),
        })
        run_generate_markdown_pages(input_path, paths, RUN_ID, fetcher=fetcher)
        source_dir = tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG
        assert (source_dir / "vendors" / "index.md").exists()
        assert (source_dir / "our-vendors" / "index.md").exists()

    def test_duplicate_candidate_url_is_fetched_only_once(self, tmp_path):
        records = [
            _candidate(VENDORS_URL, "vendor_page", lead_id="lead_1"),
            _candidate(VENDORS_URL, "vendor_page", lead_id="lead_1"),
        ]
        input_path = _make_input(tmp_path, records)
        paths = _make_paths(tmp_path)
        fetcher = _html_fetcher(**{VENDORS_URL: VENDOR_HTML})
        run_generate_markdown_pages(input_path, paths, RUN_ID, fetcher=fetcher)
        assert fetcher.requested_urls.count(VENDORS_URL) == 1

    def test_non_html_response_writes_output_record_no_markdown_no_error(self, tmp_path):
        pdf_url = f"{SOURCE_URL}brochure.pdf"
        fetcher = FakeFetcher({
            pdf_url: FakeResponse(url=pdf_url, status_code=200,
                                  content_type="application/pdf", text="")
        })
        input_path = _make_input(tmp_path, [_candidate(pdf_url, "general_market_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID, fetcher=fetcher)
        records = read_jsonl(paths.output_path)
        assert records[0]["fetch_status"] == "non_html"
        assert records[0]["markdown_path"] is None
        errors = read_jsonl(paths.errors_path)
        assert errors == []
        summary = json.loads(paths.summary_path.read_text())
        assert summary["non_html_count"] == 1

    def test_fetch_failure_writes_output_and_error_record_and_continues(self, tmp_path):
        err_url = f"{SOURCE_URL}vendors"
        fetcher = FakeFetcher(pages={}, exceptions={err_url: RuntimeError("connection refused")})
        records = [
            _candidate(err_url, "vendor_page"),
            _candidate(VISIT_URL, "hours_location_page"),
        ]
        visit_fetcher = FakeFetcher({
            **{},
            VISIT_URL: FakeResponse(url=VISIT_URL, status_code=200,
                                    content_type="text/html", text="<p>Visit us</p>"),
        }, exceptions={err_url: RuntimeError("connection refused")})
        input_path = _make_input(tmp_path, records)
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID, fetcher=visit_fetcher)
        output = read_jsonl(paths.output_path)
        assert any(r["fetch_status"] == "fetch_error" for r in output)
        assert any(r["fetch_status"] == "fetched" for r in output)
        errors = read_jsonl(paths.errors_path)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "fetch_failed"
        summary = json.loads(paths.summary_path.read_text())
        assert summary["pages_failed"] == 1
        assert summary["pages_fetched"] == 1

    def test_stage_result_is_json_serializable(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        result = run_generate_markdown_pages(input_path, paths, RUN_ID,
                                             fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        assert isinstance(result, StageResult)
        assert isinstance(json.dumps(result.to_dict()), str)

    def test_writes_only_to_provided_stage_paths_and_wiki_under_run_dir(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = StagePaths.for_stage(tmp_path, "04", "markdown_pages")
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        assert paths.output_path.exists()
        assert paths.summary_path.exists()
        assert paths.errors_path.exists()
        wiki_dir = tmp_path / "generated_wiki"
        assert wiki_dir.exists()
        assert wiki_dir.is_dir()

    def test_markdown_files_are_stable_across_repeated_runs(self, tmp_path):
        records = [_candidate(VENDORS_URL, "vendor_page")]
        fetcher = _html_fetcher(**{VENDORS_URL: VENDOR_HTML})

        input1 = _make_input(tmp_path / "run1", records)
        paths1 = StagePaths.for_stage(tmp_path / "run1", "04", "markdown_pages")
        run_generate_markdown_pages(input1, paths1, "run-id-1", fetcher=fetcher)

        input2 = _make_input(tmp_path / "run2", records)
        paths2 = StagePaths.for_stage(tmp_path / "run2", "04", "markdown_pages")
        run_generate_markdown_pages(input2, paths2, "run-id-2", fetcher=fetcher)

        md1 = (tmp_path / "run1" / "generated_wiki" / "sources" / SOURCE_SLUG / "vendors" / "index.md").read_text()
        md2 = (tmp_path / "run2" / "generated_wiki" / "sources" / SOURCE_SLUG / "vendors" / "index.md").read_text()

        assert md1 == md2
        assert "run-id-1" not in md1
        assert "run-id-2" not in md1
        assert "generated_at" not in md1
        assert f"Source: {VENDORS_URL}" in md1

    def test_does_not_read_market_registry(self, tmp_path):
        input_path = _make_input(tmp_path, [_candidate(VENDORS_URL, "vendor_page")])
        paths = _make_paths(tmp_path)
        # market_registry.jsonl deliberately absent — stage must not reference it
        registry = tmp_path / "market_registry.jsonl"
        assert not registry.exists()
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{VENDORS_URL: VENDOR_HTML}))
        assert not registry.exists()


_SHARED_NAV = "<nav><a href='/a'>SiteMenuA</a><a href='/b'>SiteMenuB</a><a href='/c'>SiteMenuC</a></nav>"
_SHARED_FOOTER = "<footer>Copyright ACME Corp. All rights reserved.</footer>"

_VENDOR_1_URL = f"{SOURCE_URL}vendor/farm-alpha"
_VENDOR_2_URL = f"{SOURCE_URL}vendor/farm-beta"
_VENDOR_3_URL = f"{SOURCE_URL}vendor/farm-gamma"

_VENDOR_1_HTML = f"<html><body>{_SHARED_NAV}<main><h1>Farm Alpha</h1><p>Sells apples.</p></main>{_SHARED_FOOTER}</body></html>"
_VENDOR_2_HTML = f"<html><body>{_SHARED_NAV}<main><h1>Farm Beta</h1><p>Sells honey.</p></main>{_SHARED_FOOTER}</body></html>"
_VENDOR_3_HTML = f"<html><body>{_SHARED_NAV}<main><h1>Farm Gamma</h1><p>Sells eggs.</p></main>{_SHARED_FOOTER}</body></html>"


class TestBoilerplateStripping:
    def _run_three_vendors(self, tmp_path):
        records = [
            _candidate(_VENDOR_1_URL, "vendor_page"),
            _candidate(_VENDOR_2_URL, "vendor_page"),
            _candidate(_VENDOR_3_URL, "vendor_page"),
        ]
        input_path = _make_input(tmp_path, records)
        paths = _make_paths(tmp_path)
        fetcher = _html_fetcher(**{
            _VENDOR_1_URL: _VENDOR_1_HTML,
            _VENDOR_2_URL: _VENDOR_2_HTML,
            _VENDOR_3_URL: _VENDOR_3_HTML,
        })
        run_generate_markdown_pages(input_path, paths, RUN_ID, fetcher=fetcher)
        return paths, tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG

    def _all_md_contents(self, source_dir):
        return [f.read_text() for f in source_dir.rglob("*.md")]

    def test_shared_nav_not_in_output_files(self, tmp_path):
        _, source_dir = self._run_three_vendors(tmp_path)
        for content in self._all_md_contents(source_dir):
            assert "SiteMenuA" not in content
            assert "SiteMenuB" not in content
            assert "SiteMenuC" not in content

    def test_shared_footer_not_in_output_files(self, tmp_path):
        _, source_dir = self._run_three_vendors(tmp_path)
        for content in self._all_md_contents(source_dir):
            assert "Copyright ACME Corp" not in content

    def test_unique_content_preserved(self, tmp_path):
        _, source_dir = self._run_three_vendors(tmp_path)
        contents = self._all_md_contents(source_dir)
        all_text = "\n".join(contents)
        assert "Sells apples" in all_text
        assert "Sells honey" in all_text
        assert "Sells eggs" in all_text

    def test_h1_vendor_name_preserved(self, tmp_path):
        _, source_dir = self._run_three_vendors(tmp_path)
        contents = self._all_md_contents(source_dir)
        all_text = "\n".join(contents)
        assert "Farm Alpha" in all_text
        assert "Farm Beta" in all_text
        assert "Farm Gamma" in all_text

    def test_source_url_footer_still_appended(self, tmp_path):
        _, source_dir = self._run_three_vendors(tmp_path)
        for content in self._all_md_contents(source_dir):
            assert "Source:" in content

    def test_single_page_falls_back_to_semantic_stripping(self, tmp_path):
        single_html = (
            "<html><body>"
            "<nav>Single Page Nav Links Here</nav>"
            "<main><h1>Market Info</h1><p>Hours: 9am to 1pm Saturday.</p></main>"
            "</body></html>"
        )
        single_url = f"{SOURCE_URL}market-info"
        input_path = _make_input(tmp_path, [_candidate(single_url, "hours_location_page")])
        paths = _make_paths(tmp_path)
        run_generate_markdown_pages(input_path, paths, RUN_ID,
                                    fetcher=_html_fetcher(**{single_url: single_html}))
        source_dir = tmp_path / "generated_wiki" / "sources" / SOURCE_SLUG
        contents = self._all_md_contents(source_dir)
        assert any("Market Info" in c for c in contents)
        assert all("Single Page Nav Links Here" not in c for c in contents)

    def test_output_records_satisfy_contract(self, tmp_path):
        paths, _ = self._run_three_vendors(tmp_path)
        records = read_jsonl(paths.output_path)
        assert len(records) == 3
        for record in records:
            require_fields(record, MARKDOWN_PAGE_REQUIRED)

    def test_summary_keys_present(self, tmp_path):
        paths, _ = self._run_three_vendors(tmp_path)
        summary = json.loads(paths.summary_path.read_text())
        assert "selected_candidates" in summary
        assert "skipped_candidates" in summary
