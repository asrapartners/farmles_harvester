import warnings
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_IGNORED_SCHEMES = ("mailto:", "tel:", "javascript:")


@dataclass
class ExtractedLink:
    raw_href: str
    discovered_url: str
    link_text: str


def extract_links_from_html(html: str, base_url: str) -> list[ExtractedLink]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[ExtractedLink] = []

    for tag in soup.find_all("a"):
        href = tag.get("href")
        if not href:
            continue
        href = href.strip()
        if not href or href.startswith("#"):
            continue
        if any(href.lower().startswith(s) for s in _IGNORED_SCHEMES):
            continue

        discovered_url = urljoin(base_url, href)
        link_text = " ".join(tag.get_text().split())

        links.append(ExtractedLink(
            raw_href=href,
            discovered_url=discovered_url,
            link_text=link_text,
        ))

    return links
