import hashlib
import re
import warnings

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

_BOILERPLATE_TAGS = frozenset(["header", "nav", "footer", "aside"])
_BOILERPLATE_PATTERNS = frozenset(["nav", "header", "footer", "menu", "sidebar", "breadcrumb"])
# Word-boundary regex so "nav" matches "site-nav" but not "navigation"
_BOILERPLATE_RE = re.compile(
    r"\b(" + "|".join(sorted(_BOILERPLATE_PATTERNS, key=len, reverse=True)) + r")\b"
)
_BLOCK_ELEMENT_TAGS = ["div", "section", "ul", "ol", "nav", "header", "footer", "aside"]
_BLOCK_CHILD_TAGS = frozenset(["div", "section", "ul", "ol", "article", "p", "header", "nav", "footer", "aside"])

_MAX_TABLE_COLS = 8  # tables wider than this are layout/grid widgets, not data tables


def _normalize_block(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _hash_block(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _table_is_layout(table_tag) -> bool:
    if table_tag.find("table"):
        return True
    max_cols = max(
        (len(row.find_all(["td", "th"])) for row in table_tag.find_all("tr")),
        default=0,
    )
    return max_cols > _MAX_TABLE_COLS


def strip_layout_tables(html: str) -> str:
    """Remove tables that are 2-D layout/calendar grids.

    Targets tables with nested <table> children (layout pattern) or more than
    _MAX_TABLE_COLS columns (calendar/grid pattern). Narrow data tables such as
    vendor lists are left intact.
    """
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        if table.parent is not None and _table_is_layout(table):
            table.decompose()
    return str(soup)


def remove_semantic_boilerplate(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    to_remove = []
    for tag in soup.find_all(True):
        if tag.name in _BOILERPLATE_TAGS:
            to_remove.append(tag)
            continue
        classes = " ".join(tag.get("class", [])).lower()
        tag_id = tag.get("id", "").lower()
        if _BOILERPLATE_RE.search(classes) or _BOILERPLATE_RE.search(tag_id):
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


def _count_html_words(html: str) -> int:
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
    return len(re.findall(r"\w+", text))


def clean_html(html: str, min_word_retention: float = 0.15) -> tuple[str, float]:
    """Apply semantic + density cleaning with a word-retention fallback.

    If the density filter would drop more than (1 - min_word_retention) of the original
    words, it is skipped and only the semantic result is returned. This prevents link-heavy
    but content-rich pages (e.g. vendor lists) from being emptied.

    Returns (cleaned_html, retention_ratio) where retention_ratio = words_after / words_before
    (1.0 when the raw page is already empty).
    """
    words_before = _count_html_words(html)

    after_semantic = remove_semantic_boilerplate(html)
    after_tables = strip_layout_tables(after_semantic)
    after_density = remove_low_density_blocks(after_tables)

    words_after = _count_html_words(after_density)
    retention = words_after / words_before if words_before > 0 else 1.0

    if words_before > 0 and retention < min_word_retention:
        words_after_tables = _count_html_words(after_tables)
        retention = words_after_tables / words_before
        return after_tables, retention

    return after_density, retention
