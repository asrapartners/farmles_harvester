from farmles_harvester.stages.generate_markdown_pages import candidate_type_to_filename
from farmles_harvester.constants import CandidateType


class TestCandidateTypeToFilename:
    def test_general_market_page(self):
        assert candidate_type_to_filename(CandidateType.GENERAL_MARKET_PAGE) == "index.md"

    def test_vendor_page(self):
        assert candidate_type_to_filename(CandidateType.VENDOR_PAGE) == "vendors.md"

    def test_hours_location_page(self):
        assert candidate_type_to_filename(CandidateType.HOURS_LOCATION_PAGE) == "visit.md"

    def test_calendar_events_page(self):
        assert candidate_type_to_filename(CandidateType.CALENDAR_EVENTS_PAGE) == "events.md"

    def test_about_contact_page(self):
        assert candidate_type_to_filename(CandidateType.ABOUT_CONTACT_PAGE) == "about.md"

    def test_unknown_type_maps_to_page_md(self):
        assert candidate_type_to_filename(CandidateType.UNKNOWN) == "page.md"

    def test_unrecognized_string_maps_to_page_md(self):
        assert candidate_type_to_filename("some_future_type") == "page.md"
