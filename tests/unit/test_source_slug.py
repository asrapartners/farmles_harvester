import pytest

from farmles_harvester.web.url_utils import source_url_to_slug


def test_simple_domain():
    assert source_url_to_slug("https://www.apexfarmersmarket.com/") == "apexfarmersmarket-com"


def test_aggregator_domain():
    assert source_url_to_slug("https://pcfma.org/") == "pcfma-org"


def test_facebook_profile():
    assert source_url_to_slug("https://www.facebook.com/apexfarmersmarket") == "facebook-com-apexfarmersmarket"


def test_trailing_slash_invariant():
    assert source_url_to_slug("https://pcfma.org") == source_url_to_slug("https://pcfma.org/")


def test_query_string_ignored():
    assert source_url_to_slug("https://www.apexfarmersmarket.com/?utm_source=test") == "apexfarmersmarket-com"
