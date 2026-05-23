import hashlib
import re
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_BOILERPLATE_TAGS = frozenset(["header", "nav", "footer", "aside"])
_BOILERPLATE_PATTERNS = frozenset(["nav", "header", "footer", "menu", "sidebar", "breadcrumb"])
_BLOCK_ELEMENT_TAGS = ["div", "section", "ul", "ol", "nav", "header", "footer", "aside"]
_BLOCK_CHILD_TAGS = frozenset(["div", "section", "ul", "ol", "article", "p", "header", "nav", "footer", "aside"])


def _normalize_block(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _hash_block(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def remove_semantic_boilerplate(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    to_remove = []
    for tag in soup.find_all(True):
        if tag.name in _BOILERPLATE_TAGS:
            to_remove.append(tag)
            continue
        classes = " ".join(tag.get("class", [])).lower()
        tag_id = tag.get("id", "").lower()
        if any(p in classes or p in tag_id for p in _BOILERPLATE_PATTERNS):
            to_remove.append(tag)

    for tag in to_remove:
        if tag.parent is not None:
            tag.decompose()

    return str(soup)


def build_boilerplate_fingerprint(
    pages: list[str],
    threshold: float = 0.8,
    min_pages: int = 3,
) -> frozenset[str]:
    if len(pages) < min_pages:
        return frozenset()

    hash_counts: dict[str, int] = {}

    for page_html in pages:
        soup = BeautifulSoup(page_html, "html.parser")
        page_hashes: set[str] = set()

        for element in soup.find_all(_BLOCK_ELEMENT_TAGS):
            text = element.get_text(strip=True)
            if not text:
                continue
            normalized = _normalize_block(text)
            if not normalized:
                continue
            h = _hash_block(normalized)
            page_hashes.add(h)

        for h in page_hashes:
            hash_counts[h] = hash_counts.get(h, 0) + 1

    n = len(pages)
    return frozenset(h for h, count in hash_counts.items() if count / n >= threshold)


def strip_fingerprinted_boilerplate(html: str, fingerprint: frozenset[str]) -> str:
    if not fingerprint:
        return html

    soup = BeautifulSoup(html, "html.parser")

    to_remove = []
    for element in soup.find_all(_BLOCK_ELEMENT_TAGS):
        text = element.get_text(strip=True)
        if not text:
            continue
        normalized = _normalize_block(text)
        if not normalized:
            continue
        if _hash_block(normalized) in fingerprint:
            to_remove.append(element)

    for element in to_remove:
        if element.parent is not None:
            element.decompose()

    return str(soup)


def remove_low_density_blocks(
    html: str,
    max_link_density: float = 0.5,
    min_text_density: float = 0.3,
) -> str:
    soup = BeautifulSoup(html, "html.parser")

    body = soup.find("body")
    if not body:
        return html

    to_remove = []
    for child in list(body.children):
        if not hasattr(child, "name") or child.name not in _BLOCK_CHILD_TAGS:
            continue
        total_text = len(child.get_text(strip=True))
        if total_text == 0:
            continue
        link_text = sum(len(a.get_text(strip=True)) for a in child.find_all("a"))
        if link_text / total_text > max_link_density:
            to_remove.append(child)

    for child in to_remove:
        child.decompose()

    return str(soup)
