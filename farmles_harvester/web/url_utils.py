import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "fbclid", "gclid",
})


@dataclass
class NormalizedUrlResult:
    input_url: str
    normalized_url: str | None
    status: str  # "normalized" | "invalid_input"
    notes: list[str]
    error_message: str | None = None


def normalize_url(raw_url: str) -> NormalizedUrlResult:
    original = raw_url
    notes: list[str] = []

    url = raw_url.strip()
    if not url:
        return NormalizedUrlResult(
            input_url=original,
            normalized_url=None,
            status="invalid_input",
            notes=notes,
            error_message="empty input",
        )

    if "://" not in url:
        url = "https://" + url
        notes.append("added https:// scheme")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return NormalizedUrlResult(
            input_url=original,
            normalized_url=None,
            status="invalid_input",
            notes=notes,
            error_message=f"unsupported scheme: {parsed.scheme!r}",
        )

    netloc = parsed.netloc.lower()

    if not netloc or " " in netloc or ("." not in netloc and netloc != "localhost"):
        return NormalizedUrlResult(
            input_url=original,
            normalized_url=None,
            status="invalid_input",
            notes=notes,
            error_message="invalid or missing domain",
        )

    path = parsed.path

    if path.startswith("/index.php/"):
        path = path[len("/index.php"):]
        notes.append("stripped /index.php front-controller prefix")
    elif path == "/index.php":
        path = "/"
        notes.append("stripped /index.php front-controller prefix")

    query = parsed.query
    if query:
        params = parse_qs(query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if k not in _TRACKING_PARAMS}
        if len(filtered) < len(params):
            notes.append("removed tracking query parameters")
        query = urlencode(filtered, doseq=True) if filtered else ""

    if not path:
        path = "/"
        notes.append("added trailing slash")

    normalized = urlunparse((parsed.scheme, netloc, path, "", query, ""))

    return NormalizedUrlResult(
        input_url=original,
        normalized_url=normalized,
        status="normalized",
        notes=notes,
    )


def source_url_to_slug(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.strip("/")
    combined = f"{host}/{path}" if path else host
    slug = re.sub(r"[^a-z0-9]+", "-", combined)
    slug = slug.strip("-")
    return slug


def is_internal_link(source_url: str, discovered_url: str) -> bool:
    def base_domain(url: str) -> str:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc

    return base_domain(source_url) == base_domain(discovered_url)
