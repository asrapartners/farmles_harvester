import pytest
from bs4 import BeautifulSoup
from markdownify import markdownify

from tests.helpers.html_factory import make_html_page
from tests.helpers.fake_fetcher import FakeResponse, FakeFetcher


def test_bs4_extracts_links():
    html = make_html_page(
        links=[
            ("/vendors", "Vendors"),
            ("/visit", "Visit Us"),
            ("https://facebook.com/apexmarket", "Facebook"),
            ("mailto:info@example.org", "Email"),
        ]
    )
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a")
    hrefs = [a["href"] for a in anchors]
    texts = [a.get_text() for a in anchors]

    assert "/vendors" in hrefs
    assert "/visit" in hrefs
    assert "https://facebook.com/apexmarket" in hrefs
    assert "mailto:info@example.org" in hrefs
    assert "Vendors" in texts
    assert "Visit Us" in texts


def test_markdownify_converts_html():
    html = make_html_page(
        body="<h1>Welcome</h1>",
        links=[("/vendors", "Vendors"), ("/visit", "Visit Us")],
    )
    md = markdownify(html)

    assert "Welcome" in md
    assert "Vendors" in md
    assert "Visit Us" in md


def test_fake_fetcher_returns_response():
    url = "https://apex.example/"
    response = FakeResponse(
        url=url,
        status_code=200,
        content_type="text/html",
        text="<html><body>Hello</body></html>",
    )
    fetcher = FakeFetcher(pages={url: response})

    result = fetcher.fetch(url)

    assert result is response
    assert url in fetcher.requested_urls


def test_fake_fetcher_raises_for_unknown_url():
    fetcher = FakeFetcher(pages={})

    with pytest.raises(KeyError):
        fetcher.fetch("https://unknown.example/")


def test_sample_html_file_parseable():
    html = make_html_page(
        links=[
            ("/vendors", "Vendors"),
            ("/visit", "Visit"),
            ("/events", "Events"),
            ("/privacy-policy", "Privacy Policy"),
        ]
    )
    soup = BeautifulSoup(html, "html.parser")
    hrefs = [a["href"] for a in soup.find_all("a")]

    assert "/vendors" in hrefs
    assert "/visit" in hrefs
    assert "/events" in hrefs
    assert "/privacy-policy" in hrefs
