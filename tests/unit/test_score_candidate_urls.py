"""
Comprehensive unit tests for the URL scoring algorithm.

Test cases are grounded in real pcfma.org crawl data. The parametrised
MUST_SELECT / MUST_REJECT tables are the primary truth — add rows to tune
the algorithm without touching the test functions themselves.
"""
import pytest

from farmles_harvester.constants import CandidateStatus, CandidateStrength, CandidateType
from farmles_harvester.stages.score_candidate_urls import LinkRecord, score_discovered_link

BASE = "https://www.pcfma.org"


def _link(url: str, text: str = "", *, internal: bool = True) -> LinkRecord:
    return LinkRecord(discovered_url=url, link_text=text, is_internal=internal)


# ---------------------------------------------------------------------------
# MUST_SELECT — algorithm must mark these SELECTED with the expected type
# fmt: off
MUST_SELECT = [
    # --- vendor pages ---
    (f"{BASE}/vendors",            "Vendors",              CandidateType.VENDOR_PAGE),
    (f"{BASE}/visit/meet-vendors", "Meet the Farmers",     CandidateType.VENDOR_PAGE),
    ("https://example.org/our-vendors", "Our Vendors",     CandidateType.VENDOR_PAGE),
    (f"{BASE}/sell",               "Sell at Our Markets",  CandidateType.VENDOR_PAGE),

    # --- location / hours ---
    (f"{BASE}/visit",              "Find a Market",        CandidateType.HOURS_LOCATION_PAGE),
    ("https://example.org/hours",  "Hours and Location",   CandidateType.HOURS_LOCATION_PAGE),
    ("https://example.org/directions", "Getting Here",     CandidateType.HOURS_LOCATION_PAGE),
    ("https://example.org/location",   "Location",         CandidateType.HOURS_LOCATION_PAGE),

    # --- market info / certified markets ---
    (f"{BASE}/Certified-Farmers-Markets",
     "Certified Farmers' Markets",                         CandidateType.GENERAL_MARKET_PAGE),
    ("https://example.org/farmers-market",
     "Farmers Market",                                     CandidateType.GENERAL_MARKET_PAGE),

    # --- events / calendar ---
    (f"{BASE}/POPClub",            "Events",               CandidateType.CALENDAR_EVENTS_PAGE),
    ("https://example.org/events/summer-festival",
     "Summer Festival",                                    CandidateType.CALENDAR_EVENTS_PAGE),
    ("https://example.org/calendar", "Calendar",           CandidateType.CALENDAR_EVENTS_PAGE),

    # --- about / contact ---
    (f"{BASE}/form/contact",       "Contact Us",           CandidateType.ABOUT_CONTACT_PAGE),
    ("https://example.org/about",  "About",                CandidateType.ABOUT_CONTACT_PAGE),
    (f"{BASE}/mission",            "Mission",              CandidateType.ABOUT_CONTACT_PAGE),
    ("https://example.org/faq",    "FAQ",                  CandidateType.ABOUT_CONTACT_PAGE),
]
# fmt: on


@pytest.mark.parametrize("url,text,exp_type", MUST_SELECT)
def test_should_be_selected(url: str, text: str, exp_type: str) -> None:
    result = score_discovered_link(_link(url, text))
    assert result.candidate_status == CandidateStatus.SELECTED, (
        f"Expected SELECTED for {url!r} (text={text!r}), "
        f"got status={result.candidate_status!r} score={result.candidate_score} "
        f"reasons={result.score_reasons}"
    )
    assert result.candidate_type == exp_type, (
        f"Expected type {exp_type!r} for {url!r}, got {result.candidate_type!r}"
    )


# ---------------------------------------------------------------------------
# MUST_REJECT — algorithm must mark these REJECTED
# fmt: off
MUST_REJECT = [
    # accessibility / EBT / SNAP / WIC program pages (low-value for wiki purposes)
    (f"{BASE}/bonus",              "Produce Bonus for Seniors FMNP & eWIC"),
    (f"{BASE}/market-match",       "Market Match CalFresh/EBT"),
    ("https://example.org/ebt-accepted",  "EBT Accepted"),
    ("https://example.org/snap-benefits", "SNAP Benefits"),
    ("https://example.org/calfresh",      "CalFresh"),

    # blog / news archive
    (f"{BASE}/blog",                        "Blog"),
    (f"{BASE}/blog/usda-grant-some-story",  "USDA Grant Story"),
    (f"{BASE}/news/2024/spring-update",     "Spring Update"),

    # tag / category pages — even when the tag name looks valuable
    (f"{BASE}/tags/news",   "News"),
    (f"{BASE}/tags/wic",    "WIC"),     # "wic" is an EBT keyword — tag penalty must dominate
    (f"{BASE}/tags/ebt",    "EBT"),     # same

    # RSS / feed
    (f"{BASE}/rss.xml",                     "Subscribe to"),  # tokeniser must catch .xml
    ("https://example.org/feed",            "RSS Feed"),

    # recipes / food content
    (f"{BASE}/recipes/cherry-arugula-salad", "Cherry Arugula Salad"),
    (f"{BASE}/eat",                          "Eat"),
    (f"{BASE}/eat/recipes",                  "Recipes"),

    # videos
    (f"{BASE}/videos/gotelli-farms",         "Gotelli Farms"),
    (f"{BASE}/videos",                       "Videos"),

    # produce / ingredient listings
    (f"{BASE}/produce/apricots",             "Apricots"),
    (f"{BASE}/produce/blueberries",          "Blueberries"),

    # pagination — paginated variants of useful pages must still be rejected
    (f"{BASE}/visit/markets?page=3&order=field_open_time&sort=desc", "Markets"),
    (f"{BASE}/?page=1",                      "More News"),
    (f"{BASE}/?page=5",                      ""),

    # CDN / infrastructure — must be rejected regardless of link text
    (f"{BASE}/cdn-cgi/l/email-protection",   "Contact Us"),

    # hard rejects
    ("https://example.org/privacy-policy",   "Privacy Policy"),
    ("https://example.org/terms-of-service", "Terms of Service"),
    ("https://example.org/cart",             "Shopping Cart"),
    ("https://example.org/login",            "Login"),
    ("https://example.org/wp-admin",         "Admin"),
    ("https://example.org/checkout",         "Checkout"),
]
# fmt: on


@pytest.mark.parametrize("url,text", MUST_REJECT)
def test_should_be_rejected(url: str, text: str) -> None:
    result = score_discovered_link(_link(url, text))
    assert result.candidate_status == CandidateStatus.REJECTED, (
        f"Expected REJECTED for {url!r} (text={text!r}), "
        f"got status={result.candidate_status!r} score={result.candidate_score} "
        f"reasons={result.score_reasons}"
    )


# ---------------------------------------------------------------------------
# Score ordering — higher-value URL must outscore lower-value URL
# fmt: off
SCORE_ORDERING = [
    # vendor page beats about page
    (f"{BASE}/vendors",      f"{BASE}/about"),
    # about page beats a blog post
    ("https://example.org/about", f"{BASE}/blog/some-post"),
    # market directory beats generic unknown page
    (f"{BASE}/Certified-Farmers-Markets", f"{BASE}/beyondthemarket"),
]
# fmt: on


@pytest.mark.parametrize("high_url,low_url", SCORE_ORDERING)
def test_score_ordering(high_url: str, low_url: str) -> None:
    high = score_discovered_link(_link(high_url))
    low = score_discovered_link(_link(low_url))
    assert high.candidate_score > low.candidate_score, (
        f"Expected {high_url!r} (score {high.candidate_score}) "
        f"> {low_url!r} (score {low.candidate_score})"
    )


# ---------------------------------------------------------------------------
# Standalone tests — invariants that don't fit the parametrised tables


def test_external_link_is_external_reference() -> None:
    result = score_discovered_link(_link("https://facebook.com/pcfma", "Facebook", internal=False))
    assert result.candidate_status == CandidateStatus.EXTERNAL_REFERENCE
    assert result.candidate_type == CandidateType.EXTERNAL_REFERENCE
    assert result.candidate_score == 0


def test_score_clamped_to_zero_minimum() -> None:
    result = score_discovered_link(_link("https://example.org/privacy-policy/login/cart", ""))
    assert result.candidate_score >= 0


def test_score_clamped_to_100_maximum() -> None:
    result = score_discovered_link(_link(
        "https://example.org/vendors/events/hours",
        "Vendors Events Hours Contact Market",
    ))
    assert result.candidate_score <= 100


def test_selected_threshold_config_override() -> None:
    # /about scores ~55; raising threshold to 70 should reject it
    result = score_discovered_link(
        _link("https://example.org/about", "About"),
        config={"selected_threshold": 70},
    )
    assert result.candidate_status == CandidateStatus.REJECTED


def test_strong_threshold_config_override() -> None:
    # /vendors scores high; lowering strong threshold means it's STRONG
    result = score_discovered_link(
        _link("https://example.org/vendors", "Vendors"),
        config={"strong_candidate_threshold": 30},
    )
    assert result.candidate_strength == CandidateStrength.STRONG


def test_candidate_strength_weak_for_low_score() -> None:
    # An unknown page with no signals stays WEAK (score 20)
    result = score_discovered_link(_link("https://example.org/xyz-unknown", "unknown page"))
    assert result.candidate_strength == CandidateStrength.WEAK


def test_score_reasons_are_populated_for_matched_signals() -> None:
    result = score_discovered_link(_link("https://example.org/vendors", "Vendors"))
    assert len(result.score_reasons) > 0
