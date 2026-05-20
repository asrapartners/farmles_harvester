from farmles_harvester.web.html_utils import extract_links_from_html

BASE_URL = "https://apex.example/"


class TestExtractLinksFromHtml:
    def test_extracts_absolute_links(self):
        html = '<a href="https://facebook.com/apexmarket">Facebook</a>'
        links = extract_links_from_html(html, BASE_URL)
        assert len(links) == 1
        assert links[0].discovered_url == "https://facebook.com/apexmarket"

    def test_resolves_relative_links(self):
        html = '<a href="/vendors">Vendors</a>'
        links = extract_links_from_html(html, BASE_URL)
        assert links[0].discovered_url == "https://apex.example/vendors"

    def test_preserves_link_text(self):
        html = '<a href="/vendors">Our Vendors</a>'
        links = extract_links_from_html(html, BASE_URL)
        assert links[0].link_text == "Our Vendors"

    def test_ignores_empty_href(self):
        html = '<a href="">Click here</a>'
        links = extract_links_from_html(html, BASE_URL)
        assert len(links) == 0

    def test_ignores_fragment_only_href(self):
        html = '<a href="#top">Back to top</a>'
        links = extract_links_from_html(html, BASE_URL)
        assert len(links) == 0

    def test_ignores_javascript_href(self):
        html = '<a href="javascript:void(0)">Click</a>'
        links = extract_links_from_html(html, BASE_URL)
        assert len(links) == 0

    def test_ignores_mailto_href(self):
        html = '<a href="mailto:info@example.org">Email</a>'
        links = extract_links_from_html(html, BASE_URL)
        assert len(links) == 0

    def test_ignores_tel_href(self):
        html = '<a href="tel:+1234567890">Call Us</a>'
        links = extract_links_from_html(html, BASE_URL)
        assert len(links) == 0

    def test_handles_nested_elements_inside_anchor(self):
        html = '<a href="/vendors"><span>Our <strong>Vendors</strong></span></a>'
        links = extract_links_from_html(html, BASE_URL)
        assert links[0].link_text == "Our Vendors"
