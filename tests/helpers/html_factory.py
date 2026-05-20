def make_html_page(
    title: str = "Test Page",
    links: list[tuple[str, str]] | None = None,
    body: str = "",
) -> str:
    link_tags = "\n".join(
        f'<a href="{href}">{text}</a>' for href, text in (links or [])
    )
    return f"""<!DOCTYPE html>
<html>
<head><title>{title}</title></head>
<body>
{body}
{link_tags}
</body>
</html>"""
