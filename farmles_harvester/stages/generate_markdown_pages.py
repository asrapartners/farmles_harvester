from farmles_harvester.constants import CandidateType

_TYPE_TO_FILENAME: dict[str, str] = {
    CandidateType.GENERAL_MARKET_PAGE: "index.md",
    CandidateType.VENDOR_PAGE: "vendors.md",
    CandidateType.HOURS_LOCATION_PAGE: "visit.md",
    CandidateType.CALENDAR_EVENTS_PAGE: "events.md",
    CandidateType.ABOUT_CONTACT_PAGE: "about.md",
}


def candidate_type_to_filename(candidate_type: str) -> str:
    return _TYPE_TO_FILENAME.get(candidate_type, "page.md")
