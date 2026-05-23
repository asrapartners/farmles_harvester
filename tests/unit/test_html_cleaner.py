from farmles_harvester.web.html_cleaner import (
    build_boilerplate_fingerprint,
    remove_low_density_blocks,
    remove_semantic_boilerplate,
    strip_fingerprinted_boilerplate,
)


class TestRemoveSemanticBoilerplate:
    def test_strips_nav_tag(self):
        html = "<html><body><nav>menu</nav><main>content</main></body></html>"
        result = remove_semantic_boilerplate(html)
        assert "content" in result
        assert "menu" not in result

    def test_strips_header_and_footer_tags(self):
        html = "<html><body><header>logo</header><article>story</article><footer>©</footer></body></html>"
        result = remove_semantic_boilerplate(html)
        assert "story" in result
        assert "logo" not in result
        assert "©" not in result

    def test_strips_element_by_class_name(self):
        html = "<html><body><div class='nav-menu'>nav</div><div class='content'>body</div></body></html>"
        result = remove_semantic_boilerplate(html)
        assert "body" in result
        assert "nav" not in result

    def test_strips_element_by_id(self):
        html = "<html><body><div id='main-header'>header</div><div id='page-content'>article</div></body></html>"
        result = remove_semantic_boilerplate(html)
        assert "article" in result
        assert "header" not in result

    def test_passes_clean_html_unchanged(self):
        html = "<html><body><h1>Title</h1><p>Text</p></body></html>"
        result = remove_semantic_boilerplate(html)
        assert "Title" in result
        assert "Text" in result


class TestBuildBoilerplateFingerprint:
    def test_identifies_block_present_in_all_pages(self):
        nav_html = "<nav>Menu A | Menu B | Menu C</nav>"
        pages = [
            f"<html><body>{nav_html}<div>Page {i} unique body text here.</div></body></html>"
            for i in range(5)
        ]
        fp = build_boilerplate_fingerprint(pages)

        test_html = f"<html><body>{nav_html}<div>New page unique content.</div></body></html>"
        result = strip_fingerprinted_boilerplate(test_html, fp)
        assert "Menu A" not in result
        assert "New page unique content" in result

    def test_returns_empty_for_single_page(self):
        pages = ["<html><body><nav>Nav</nav><p>Content</p></body></html>"]
        fp = build_boilerplate_fingerprint(pages, min_pages=3)
        assert fp == frozenset()

    def test_returns_empty_for_fewer_than_min_pages(self):
        pages = [
            "<html><body><nav>Nav</nav><p>Page 1</p></body></html>",
            "<html><body><nav>Nav</nav><p>Page 2</p></body></html>",
        ]
        fp = build_boilerplate_fingerprint(pages, min_pages=3)
        assert fp == frozenset()

    def test_threshold_below_cutoff_excluded(self):
        common_nav = "<nav>Site Navigation Block</nav>"
        pages = [
            f"<html><body>{common_nav if i < 6 else ''}<div>Page {i} content</div></body></html>"
            for i in range(10)
        ]
        fp = build_boilerplate_fingerprint(pages, threshold=0.8, min_pages=3)

        test_html = f"<html><body>{common_nav}<div>Test content</div></body></html>"
        result = strip_fingerprinted_boilerplate(test_html, fp)
        assert "Site Navigation Block" in result

    def test_threshold_above_cutoff_included(self):
        common_nav = "<nav>Site Navigation Block</nav>"
        pages = [
            f"<html><body>{common_nav if i < 9 else ''}<div>Page {i} content</div></body></html>"
            for i in range(10)
        ]
        fp = build_boilerplate_fingerprint(pages, threshold=0.8, min_pages=3)

        test_html = f"<html><body>{common_nav}<div>Test content</div></body></html>"
        result = strip_fingerprinted_boilerplate(test_html, fp)
        assert "Site Navigation Block" not in result

    def test_unique_content_not_fingerprinted(self):
        pages = [
            f"<html><body><nav>Site Nav Link1 Link2</nav><div>Unique body text {i}</div></body></html>"
            for i in range(5)
        ]
        fp = build_boilerplate_fingerprint(pages)

        test_html = "<html><body><div>Unique body text 99</div></body></html>"
        result = strip_fingerprinted_boilerplate(test_html, fp)
        assert "Unique body text 99" in result


class TestStripFingerprintedBoilerplate:
    def test_removes_fingerprinted_node(self):
        nav_html = "<nav>Repeated Nav Block</nav>"
        pages = [
            f"<html><body>{nav_html}<div>Page {i} unique</div></body></html>"
            for i in range(3)
        ]
        fp = build_boilerplate_fingerprint(pages, min_pages=3)

        test_html = f"<html><body>{nav_html}<div>Test unique content</div></body></html>"
        result = strip_fingerprinted_boilerplate(test_html, fp)
        assert "Repeated Nav Block" not in result
        assert "Test unique content" in result

    def test_preserves_non_fingerprinted_node(self):
        fp = build_boilerplate_fingerprint(
            ["<html><body><nav>Nav</nav><div>Page {i}</div></body></html>".replace("{i}", str(i)) for i in range(3)],
            min_pages=3,
        )
        test_html = "<html><body><div>Completely different content here</div></body></html>"
        result = strip_fingerprinted_boilerplate(test_html, fp)
        assert "Completely different content here" in result

    def test_empty_fingerprint_returns_html_unchanged(self):
        html = "<html><body><nav>Nav</nav><p>Content</p></body></html>"
        result = strip_fingerprinted_boilerplate(html, frozenset())
        assert "Nav" in result
        assert "Content" in result


class TestRemoveLowDensityBlocks:
    def test_strips_link_only_block(self):
        html = (
            "<body>"
            "<div><a href='/1'>L1</a><a href='/2'>L2</a><a href='/3'>L3</a></div>"
            "<p>Real content paragraph with sufficient text.</p>"
            "</body>"
        )
        result = remove_low_density_blocks(html)
        assert "Real content paragraph" in result
        assert "L1" not in result

    def test_preserves_content_block(self):
        long_text = "This is a long paragraph with lots of real informational content about the subject."
        html = f"<body><p>{long_text} <a href='/more'>read more</a></p></body>"
        result = remove_low_density_blocks(html)
        assert long_text[:30] in result

    def test_block_at_threshold_boundary(self):
        # link_density = 5/10 = 0.5 exactly — threshold is exclusive (> 0.5), so block is kept
        html = "<body><div>AAAAA<a href='/'>BBBBB</a></div></body>"
        result = remove_low_density_blocks(html)
        assert "AAAAA" in result
