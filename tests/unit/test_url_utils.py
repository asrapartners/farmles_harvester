from farmles_harvester.web.url_utils import normalize_url, is_internal_link


class TestNormalizeUrl:
    def test_adds_https_scheme(self):
        result = normalize_url("apexfarmersmarket.com")
        assert result.status == "normalized"
        assert result.normalized_url.startswith("https://")

    def test_trims_whitespace(self):
        result = normalize_url("  https://example.com/page  ")
        assert result.status == "normalized"
        assert result.normalized_url == "https://example.com/page"

    def test_lowercases_domain(self):
        result = normalize_url("https://Example.COM/path")
        assert result.status == "normalized"
        assert result.normalized_url.startswith("https://example.com/")

    def test_does_not_lowercase_path(self):
        result = normalize_url("https://example.com/MyPath/SubDir")
        assert result.status == "normalized"
        assert "/MyPath/SubDir" in result.normalized_url

    def test_removes_fragment(self):
        result = normalize_url("https://example.com/page#section")
        assert result.status == "normalized"
        assert "#" not in result.normalized_url

    def test_removes_tracking_params(self):
        result = normalize_url(
            "https://example.com/page?utm_source=test&utm_medium=email&q=farmers"
        )
        assert result.status == "normalized"
        assert "utm_source" not in result.normalized_url
        assert "utm_medium" not in result.normalized_url
        assert "q=farmers" in result.normalized_url

    def test_keeps_non_tracking_params(self):
        result = normalize_url("https://example.com/search?q=market&sort=name")
        assert result.status == "normalized"
        assert "q=" in result.normalized_url
        assert "sort=" in result.normalized_url

    def test_adds_trailing_slash_for_bare_domain(self):
        result = normalize_url("apexfarmersmarket.com")
        assert result.status == "normalized"
        assert result.normalized_url == "https://apexfarmersmarket.com/"

    def test_rejects_malformed_input(self):
        result = normalize_url("not a url at all !!!")
        assert result.status == "invalid_input"
        assert result.normalized_url is None

    def test_does_not_make_network_calls(self):
        # A domain guaranteed not to resolve; normalize_url must not try
        result = normalize_url("https://this-domain-does-not-exist.invalid/page")
        assert result.status == "normalized"


class TestIsInternalLink:
    def test_same_domain_is_internal(self):
        assert is_internal_link("https://example.org/", "https://example.org/vendors") is True

    def test_www_and_non_www_are_same(self):
        assert is_internal_link("https://www.example.org/", "https://example.org/vendors") is True

    def test_different_domain_is_external(self):
        assert is_internal_link("https://example.org/", "https://facebook.com/example") is False

    def test_non_www_subdomain_is_external(self):
        assert is_internal_link("https://example.org/", "https://blog.example.org/post") is False
