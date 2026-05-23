from farmles_harvester.wiki.markdown_cleaner import (
    build_md_fingerprint,
    normalize_md_block,
    strip_md_fingerprint,
)

_SHARED_NAV = "\n".join([
    "## Main navigation",
    "",
    "* [Visit](/visit)",
    "* [Eat](/eat)",
    "* [About](/about)",
])

_SHARED_FOOTER = "\n".join([
    "© Pacific Coast Farmers Market Association",
    "",
    "[Job opportunities](/jobs) [Contact](/contact)",
])


class TestNormalizeMdBlock:
    def test_strips_link_syntax(self):
        result = normalize_md_block("[Visit](/visit)")
        assert result == "Visit"

    def test_strips_image_syntax(self):
        result = normalize_md_block("![Logo](/logo.png)")
        assert result == "Logo"

    def test_strips_heading_markers(self):
        result = normalize_md_block("## Main navigation")
        assert result == "Main navigation"

    def test_strips_formatting_chars(self):
        result = normalize_md_block("**bold** _italic_")
        assert result == "bold italic"

    def test_collapses_whitespace(self):
        result = normalize_md_block("  lots   of    spaces  ")
        assert result == "lots of spaces"


class TestBuildMdFingerprint:
    def _make_files(self, n, shared_block, unique_prefix="Unique content page"):
        return [
            f"{shared_block}\n\n{unique_prefix} {i} with enough text to be distinct."
            for i in range(n)
        ]

    def test_identifies_shared_block(self):
        files = self._make_files(5, _SHARED_NAV)
        fp = build_md_fingerprint(files)
        result = strip_md_fingerprint(files[0], fp)
        assert "Visit" not in result
        assert "Unique content page 0" in result

    def test_returns_empty_below_min_files(self):
        files = self._make_files(2, _SHARED_NAV)
        fp = build_md_fingerprint(files, min_files=3)
        assert fp == frozenset()

    def test_threshold_respected(self):
        # block in 6/10 files = 60% < 80% threshold → not fingerprinted
        files = [
            f"{_SHARED_NAV}\n\nPage {i} content here." if i < 6
            else f"Page {i} content here."
            for i in range(10)
        ]
        fp = build_md_fingerprint(files, threshold=0.8, min_files=3)
        result = strip_md_fingerprint(files[0], fp)
        assert "Visit" in result  # nav NOT stripped (below threshold)

    def test_unique_blocks_not_fingerprinted(self):
        files = [
            f"{_SHARED_NAV}\n\nFarm {i} sells {'apples' if i % 2 == 0 else 'honey'} and grows unique crop {i}."
            for i in range(5)
        ]
        fp = build_md_fingerprint(files)
        # Unique content must survive
        result = strip_md_fingerprint(files[0], fp)
        assert "Farm 0" in result


class TestStripMdFingerprint:
    def test_removes_fingerprinted_block(self):
        files = [
            f"{_SHARED_NAV}\n\nPage {i} unique content."
            for i in range(3)
        ]
        fp = build_md_fingerprint(files, min_files=3)
        result = strip_md_fingerprint(files[0], fp)
        assert "Visit" not in result
        assert "Page 0 unique content" in result

    def test_preserves_non_fingerprinted_block(self):
        fp = build_md_fingerprint(
            [f"{_SHARED_NAV}\n\nPage {i}." for i in range(3)],
            min_files=3,
        )
        unrelated = "This block is completely different and appears nowhere else."
        result = strip_md_fingerprint(f"{_SHARED_NAV}\n\n{unrelated}", fp)
        assert unrelated in result

    def test_empty_fingerprint_unchanged(self):
        content = f"{_SHARED_NAV}\n\nSome content."
        result = strip_md_fingerprint(content, frozenset())
        assert result == content.strip()

    def test_source_footer_preserved(self):
        # Source footer is unique per file (different URL each time) → never fingerprinted
        files = [
            f"{_SHARED_NAV}\n\nPage {i} content.\n\n---\n\nSource: https://example.com/page/{i}"
            for i in range(5)
        ]
        fp = build_md_fingerprint(files)
        result = strip_md_fingerprint(files[0], fp)
        assert "Source: https://example.com/page/0" in result
