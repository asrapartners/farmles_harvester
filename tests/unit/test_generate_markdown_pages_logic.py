from pathlib import Path

from farmles_harvester.stages.generate_markdown_pages import candidate_url_to_rel_path


class TestCandidateUrlToRelPath:
    def test_root_url_returns_index_md(self):
        assert candidate_url_to_rel_path("https://example.com/") == Path("index.md")

    def test_root_url_without_slash_returns_index_md(self):
        assert candidate_url_to_rel_path("https://example.com") == Path("index.md")

    def test_single_segment_path(self):
        assert candidate_url_to_rel_path("https://example.com/vendors") == Path("vendors/index.md")

    def test_trailing_slash_is_normalised(self):
        assert candidate_url_to_rel_path("https://example.com/vendors/") == Path("vendors/index.md")

    def test_nested_path(self):
        result = candidate_url_to_rel_path("https://example.com/market/apex/vendors/")
        assert result == Path("market/apex/vendors/index.md")

    def test_hyphenated_segment(self):
        assert candidate_url_to_rel_path("https://example.com/our-vendors") == Path("our-vendors/index.md")
