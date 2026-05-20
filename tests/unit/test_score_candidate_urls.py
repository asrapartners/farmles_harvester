from farmles_harvester.stages.score_candidate_urls import score_discovered_link, LinkRecord
from farmles_harvester.constants import CandidateType, CandidateStatus, CandidateStrength


def _internal(url: str, text: str) -> LinkRecord:
    return LinkRecord(discovered_url=url, link_text=text, is_internal=True)


def _external(url: str, text: str) -> LinkRecord:
    return LinkRecord(discovered_url=url, link_text=text, is_internal=False)


class TestScoreDiscoveredLink:
    def test_vendors_page_is_selected_as_vendor_page(self):
        result = score_discovered_link(_internal("https://example.org/vendors", "Vendors"))
        assert result.candidate_status == CandidateStatus.SELECTED
        assert result.candidate_type == CandidateType.VENDOR_PAGE
        assert result.candidate_score >= 40

    def test_visit_page_is_hours_location(self):
        result = score_discovered_link(_internal("https://example.org/visit", "Visit Us"))
        assert result.candidate_status == CandidateStatus.SELECTED
        assert result.candidate_type == CandidateType.HOURS_LOCATION_PAGE

    def test_events_page_is_calendar_events(self):
        result = score_discovered_link(_internal("https://example.org/events", "Events"))
        assert result.candidate_status == CandidateStatus.SELECTED
        assert result.candidate_type == CandidateType.CALENDAR_EVENTS_PAGE

    def test_contact_page_is_about_contact(self):
        result = score_discovered_link(_internal("https://example.org/contact", "Contact"))
        assert result.candidate_type == CandidateType.ABOUT_CONTACT_PAGE

    def test_privacy_policy_is_rejected_as_low_value(self):
        result = score_discovered_link(_internal("https://example.org/privacy-policy", "Privacy Policy"))
        assert result.candidate_status == CandidateStatus.REJECTED
        assert result.candidate_type == CandidateType.LOW_VALUE_PAGE

    def test_old_blog_link_is_penalized(self):
        baseline = score_discovered_link(_internal("https://example.org/about", "About"))
        blog = score_discovered_link(_internal("https://example.org/blog/2019/old-post", "Old Post"))
        assert blog.candidate_score < baseline.candidate_score

    def test_external_link_is_external_reference(self):
        result = score_discovered_link(_external("https://facebook.com/example", "Facebook"))
        assert result.candidate_status == CandidateStatus.EXTERNAL_REFERENCE
        assert result.candidate_type == CandidateType.EXTERNAL_REFERENCE

    def test_score_clamped_to_zero_minimum(self):
        result = score_discovered_link(_internal("https://example.org/privacy-policy", "Privacy Policy"))
        assert result.candidate_score >= 0

    def test_score_clamped_to_100_maximum(self):
        # Multiple stacking positive signals push raw score above 100
        result = score_discovered_link(_internal(
            "https://example.org/vendors/events/hours",
            "Vendors Events Hours Contact Market",
        ))
        assert result.candidate_score <= 100

    def test_candidate_strength_assigned_correctly(self):
        strong = score_discovered_link(_internal("https://example.org/vendors", "Vendors"))
        assert strong.candidate_strength == CandidateStrength.STRONG

        weak = score_discovered_link(_internal("https://example.org/unknown-xyz-page", "Unknown"))
        assert weak.candidate_strength == CandidateStrength.WEAK
