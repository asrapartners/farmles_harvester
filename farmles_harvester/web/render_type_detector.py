from bs4 import BeautifulSoup

# Raw text patterns that appear inside <script> tags for common JS frameworks.
# Ordered roughly by specificity.
_JS_DATA_MARKERS: list[tuple[str, str]] = [
    ("window.__NEXT_DATA__", "next_data"),
    ("window.__NUXT__", "nuxt_state"),
    ("window.__remixContext", "remix_context"),
    ("window.__INITIAL_STATE__", "initial_state"),
    ("window.__REDUX_STATE__", "redux_state"),
    ("window.__APOLLO_STATE__", "apollo_state"),
]

# HTML attributes that only framework-rendered markup ever carries.
_JS_ATTR_MARKERS: list[tuple[str, str]] = [
    ("data-reactroot", "react_root_attr"),
    ("ng-version", "angular_ng_version"),
    ("data-vue-meta", "vue_meta_attr"),
    ("data-n-head", "nuxt_n_head_attr"),
]

# div IDs that SPAs use as mount points. Flagged only when the element is
# nearly empty (JS hasn't run to populate it).
_SPA_SHELL_IDS: list[str] = ["root", "app", "__next", "app-root", "react-root", "ng-app"]

_BODY_TEXT_RATIO_STATIC_THRESHOLD = 0.10
_SPA_SHELL_MAX_TEXT = 50


def detect_render_type(html: str) -> tuple[str, dict]:
    """Heuristically classify an HTML page as static or JS-rendered.

    Returns (render_type, evidence) where render_type is one of:
      "static_html" – server-rendered, readable content present
      "dynamic_js"  – SPA shell or JS-injected content detected
      "unknown"     – insufficient signal either way
    """
    if not html or not html.strip():
        return "unknown", {"reason": "empty_html"}

    # --- fast pass: raw-text JS data blob markers -------------------------
    for needle, name in _JS_DATA_MARKERS:
        if needle in html:
            return "dynamic_js", {"marker": name}

    # --- structural parse -------------------------------------------------
    soup = BeautifulSoup(html, "html.parser")

    # framework HTML attributes
    for attr, name in _JS_ATTR_MARKERS:
        if soup.find(attrs={attr: True}):
            return "dynamic_js", {"marker": name}

    # near-empty SPA mount points
    for shell_id in _SPA_SHELL_IDS:
        tag = soup.find(id=shell_id)
        if tag is not None and len(tag.get_text(strip=True)) < _SPA_SHELL_MAX_TEXT:
            return "dynamic_js", {"marker": f"empty_shell#{shell_id}"}

    # --- body text density ------------------------------------------------
    body = soup.find("body") or soup
    visible_text = body.get_text(separator=" ", strip=True)
    ratio = len(visible_text) / len(html)
    script_count = len(soup.find_all("script"))
    evidence = {"body_text_ratio": round(ratio, 3), "script_count": script_count}

    if ratio >= _BODY_TEXT_RATIO_STATIC_THRESHOLD:
        return "static_html", evidence

    return "unknown", evidence
