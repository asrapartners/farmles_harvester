class CandidateType:
    VENDOR_PAGE = "vendor_page"
    HOURS_LOCATION_PAGE = "hours_location_page"
    CALENDAR_EVENTS_PAGE = "calendar_events_page"
    ABOUT_CONTACT_PAGE = "about_contact_page"
    GENERAL_MARKET_PAGE = "general_market_page"
    EXTERNAL_REFERENCE = "external_reference"
    LOW_VALUE_PAGE = "low_value_page"
    UNKNOWN = "unknown"


class CandidateStatus:
    SELECTED = "selected"
    REJECTED = "rejected"
    EXTERNAL_REFERENCE = "external_reference"


class CandidateStrength:
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class SourceRelevanceLabel:
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    UNCERTAIN = "uncertain"
    LOW_CONFIDENCE = "low_confidence"
