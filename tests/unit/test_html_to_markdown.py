import pytest

from farmles_harvester.stages.generate_markdown_pages import (
    compute_content_hash,
    html_to_markdown,
    normalize_markdown,
)

SOURCE_URL = "https://example.org/vendors"


class TestHtmlToMarkdown:
    def test_preserves_heading_text(self):
        result = html_to_markdown("<h1>Apex Farmers Market</h1>", SOURCE_URL)
        assert "# Apex Farmers Market" in result

    def test_preserves_factual_paragraph_text(self):
        html = "<p>Hours: Saturdays 8 AM to 12 PM</p><p>Location: 123 Main Street, Apex, NC</p>"
        result = html_to_markdown(html, SOURCE_URL)
        assert "Hours: Saturdays 8 AM to 12 PM" in result
        assert "Location: 123 Main Street, Apex, NC" in result

    def test_preserves_list_content(self):
        html = "<ul><li>Smith Farm - vegetables and eggs</li><li>Blue Ridge Bakery - bread and pastries</li></ul>"
        result = html_to_markdown(html, SOURCE_URL)
        assert "Smith Farm - vegetables and eggs" in result
        assert "Blue Ridge Bakery - bread and pastries" in result

    def test_preserves_link_text(self):
        html = '<a href="https://example.org/vendors">Vendors</a>'
        result = html_to_markdown(html, SOURCE_URL)
        assert "Vendors" in result

    def test_appends_source_url_footer(self):
        result = html_to_markdown("<p>text</p>", SOURCE_URL)
        assert f"Source: {SOURCE_URL}" in result

    def test_removes_trailing_whitespace(self):
        html = "<p>Some text</p>"
        result = html_to_markdown(html, SOURCE_URL)
        for line in result.splitlines():
            assert line == line.rstrip()

    def test_collapses_excessive_blank_lines(self):
        html = "<p>line one</p><br/><br/><br/><p>line two</p>"
        result = html_to_markdown(html, SOURCE_URL)
        assert "\n\n\n" not in result

    def test_does_not_remove_factual_content_during_cleanup(self):
        html = (
            "<h1>Apex Farmers Market</h1>"
            "<p>Hours: Saturdays 8 AM to 12 PM</p>"
            "<p>Season: April through October</p>"
            "<p>Location: 123 Main Street, Apex, NC</p>"
        )
        result = html_to_markdown(html, SOURCE_URL)
        assert "Apex Farmers Market" in result
        assert "Hours: Saturdays 8 AM to 12 PM" in result
        assert "Season: April through October" in result
        assert "Location: 123 Main Street, Apex, NC" in result


class TestNormalizeMarkdown:
    def test_strips_trailing_whitespace_independently(self):
        result = normalize_markdown("# Title   \n\nSome text   ")
        for line in result.splitlines():
            assert line == line.rstrip()

    def test_collapses_consecutive_blank_lines_independently(self):
        result = normalize_markdown("line one\n\n\n\nline two")
        assert "\n\n\n" not in result
        assert "line one" in result
        assert "line two" in result

    def test_returns_empty_string_for_blank_input(self):
        assert normalize_markdown("") == ""
        assert normalize_markdown("   \n\n   ") == ""


class TestComputeContentHash:
    def test_returns_sha256_prefixed_string(self):
        result = compute_content_hash("hello")
        assert result.startswith("sha256:")
        assert len(result) == len("sha256:") + 64

    def test_is_deterministic(self):
        assert compute_content_hash("hello") == compute_content_hash("hello")

    def test_differs_for_different_inputs(self):
        assert compute_content_hash("hello") != compute_content_hash("world")


class TestStability:
    HTML = "<h1>Vendors</h1><ul><li>Smith Farm - vegetables and eggs</li></ul>"
    URL = "https://apex.example/vendors"

    def test_html_to_markdown_is_deterministic(self):
        assert html_to_markdown(self.HTML, self.URL) == html_to_markdown(self.HTML, self.URL)

    def test_markdown_does_not_contain_volatile_metadata(self):
        result = html_to_markdown(self.HTML, self.URL)
        assert "generated_at" not in result
        assert "Generated at" not in result
        assert "run_id" not in result
        assert "Run ID" not in result
        assert f"Source: {self.URL}" in result

    def test_normalize_markdown_is_deterministic(self):
        raw = "# Title   \n\n\n\nSome text   \n\n"
        assert normalize_markdown(raw) == normalize_markdown(raw)


class TestDirtyHtmlEdgeCases:
    def test_malformed_unclosed_html_does_not_crash(self):
        html = "<h1>Apex Market<p>Hours: Saturdays 8 AM"
        result = html_to_markdown(html, "https://example.org/")
        assert "Apex Market" in result
        assert "Hours: Saturdays 8 AM" in result

    def test_empty_html_does_not_crash_and_appends_footer(self):
        result = html_to_markdown("", "https://example.org/")
        assert "Source: https://example.org/" in result

    def test_script_style_only_html_does_not_crash(self):
        html = "<style>body { color: red; }</style><script>alert('hi');</script>"
        result = html_to_markdown(html, "https://example.org/")
        assert "Source: https://example.org/" in result

    def test_excessive_whitespace_is_normalized(self):
        html = "<p>Some   text   with   extra   spaces</p>"
        result = html_to_markdown(html, "https://example.org/")
        assert "\n\n\n" not in result

    def test_empty_source_url_raises_value_error(self):
        with pytest.raises(ValueError):
            html_to_markdown("<p>text</p>", "")
