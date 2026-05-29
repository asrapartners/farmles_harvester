import pytest

from farmles_harvester.web.render_type_detector import detect_render_type


# ── helpers ────────────────────────────────────────────────────────────────

def _static_page(body_text: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html>
<head><title>Test</title><meta charset="UTF-8">{extra_head}</head>
<body>{body_text}</body>
</html>"""


_RICH_BODY = " ".join(["word"] * 200)  # well above text-density threshold


# ── static HTML ────────────────────────────────────────────────────────────

class TestStaticHtml:
    def test_plain_page_with_lots_of_text(self):
        html = _static_page(f"<p>{_RICH_BODY}</p>")
        render_type, evidence = detect_render_type(html)
        assert render_type == "static_html"
        assert evidence["body_text_ratio"] >= 0.10

    def test_includes_script_count_in_evidence(self):
        html = _static_page(
            f"<p>{_RICH_BODY}</p>",
            extra_head='<script src="/app.js"></script>',
        )
        _, evidence = detect_render_type(html)
        assert "script_count" in evidence

    def test_static_page_with_non_spa_id(self):
        # An element with id="content" should not trigger SPA detection
        html = _static_page(f'<div id="content"><p>{_RICH_BODY}</p></div>')
        render_type, _ = detect_render_type(html)
        assert render_type == "static_html"


# ── dynamic JS – data blob markers ─────────────────────────────────────────

class TestJsDataBlobMarkers:
    def test_next_data_blob(self):
        html = _static_page(
            "<div id='__next'></div>",
            extra_head='<script id="__NEXT_DATA__" type="application/json">'
                       'window.__NEXT_DATA__ = {"props":{}}</script>',
        )
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "next_data"

    def test_nuxt_state_blob(self):
        html = _static_page(
            "<div id='app'></div>",
            extra_head="<script>window.__NUXT__={}</script>",
        )
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "nuxt_state"

    def test_remix_context_blob(self):
        html = _static_page(
            "<div id='root'></div>",
            extra_head="<script>window.__remixContext = {}</script>",
        )
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "remix_context"

    def test_initial_state_blob(self):
        html = _static_page(
            "",
            extra_head="<script>window.__INITIAL_STATE__={}</script>",
        )
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "initial_state"

    def test_redux_state_blob(self):
        html = _static_page(
            "",
            extra_head="<script>window.__REDUX_STATE__={}</script>",
        )
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "redux_state"

    def test_apollo_state_blob(self):
        html = _static_page(
            "",
            extra_head="<script>window.__APOLLO_STATE__={}</script>",
        )
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "apollo_state"


# ── dynamic JS – attribute markers ─────────────────────────────────────────

class TestJsAttrMarkers:
    def test_react_root_attr(self):
        html = _static_page(f'<div data-reactroot=""><p>{_RICH_BODY}</p></div>')
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "react_root_attr"

    def test_angular_ng_version(self):
        html = _static_page(f'<app-root ng-version="15.0.0">{_RICH_BODY}</app-root>')
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "angular_ng_version"

    def test_vue_meta_attr(self):
        html = _static_page(f'<div data-vue-meta="true">{_RICH_BODY}</div>')
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "vue_meta_attr"

    def test_nuxt_n_head_attr(self):
        html = _static_page(f'<head data-n-head="true"><title>x</title></head>'
                             f'<body>{_RICH_BODY}</body>')
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == "nuxt_n_head_attr"


# ── dynamic JS – empty SPA shell ───────────────────────────────────────────

class TestSpaShells:
    @pytest.mark.parametrize("shell_id", ["root", "app", "__next", "app-root", "react-root", "ng-app"])
    def test_empty_shell_ids(self, shell_id):
        html = _static_page(f'<div id="{shell_id}"></div>')
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert evidence["marker"] == f"empty_shell#{shell_id}"

    def test_root_div_with_real_content_is_not_flagged(self):
        html = _static_page(f'<div id="root"><p>{_RICH_BODY}</p></div>')
        render_type, _ = detect_render_type(html)
        # Has real content → should NOT be flagged as empty shell
        assert render_type != "dynamic_js"

    def test_app_div_with_whitespace_only_is_shell(self):
        html = _static_page('<div id="app">   \n   </div>')
        render_type, evidence = detect_render_type(html)
        assert render_type == "dynamic_js"
        assert "app" in evidence["marker"]


# ── unknown ────────────────────────────────────────────────────────────────

class TestUnknown:
    def test_empty_string(self):
        render_type, evidence = detect_render_type("")
        assert render_type == "unknown"
        assert evidence.get("reason") == "empty_html"

    def test_whitespace_only(self):
        render_type, evidence = detect_render_type("   \n   ")
        assert render_type == "unknown"

    def test_sparse_html_no_markers(self):
        # Minimal page: very little text, no JS markers
        html = "<html><head></head><body><div></div></body></html>"
        render_type, _ = detect_render_type(html)
        assert render_type == "unknown"

    def test_thin_page_with_few_words(self):
        html = _static_page("<p>Hello world</p>")
        render_type, evidence = detect_render_type(html)
        # Three words in a full HTML document → ratio well below threshold
        assert render_type == "unknown"
        assert evidence["body_text_ratio"] < 0.10


# ── evidence structure ─────────────────────────────────────────────────────

class TestEvidenceStructure:
    def test_static_evidence_has_ratio_and_script_count(self):
        html = _static_page(f"<p>{_RICH_BODY}</p>")
        _, evidence = detect_render_type(html)
        assert "body_text_ratio" in evidence
        assert "script_count" in evidence
        assert isinstance(evidence["body_text_ratio"], float)
        assert isinstance(evidence["script_count"], int)

    def test_dynamic_marker_evidence_is_string(self):
        html = _static_page("", extra_head="<script>window.__NEXT_DATA__={}</script>")
        _, evidence = detect_render_type(html)
        assert isinstance(evidence["marker"], str)

    def test_ratio_is_rounded_to_three_decimals(self):
        html = _static_page(f"<p>{_RICH_BODY}</p>")
        _, evidence = detect_render_type(html)
        # Should have at most 3 decimal places
        ratio_str = str(evidence["body_text_ratio"])
        decimal_part = ratio_str.split(".")[-1] if "." in ratio_str else ""
        assert len(decimal_part) <= 3
