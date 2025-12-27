from __future__ import annotations

import mistune


def slugify(text: str, max_length: int | None = 100) -> str:
    """Convert text to a URL-friendly slug.

    Args:
        text: The text to convert to a slug.
        max_length: Maximum length of the resulting slug. If None, no
            truncation. Defaults to 100 to leave room for timestamps and
            extensions.
    """
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug or "page"

    if max_length is not None and len(slug) > max_length:
        # Truncate and remove any trailing hyphen from the cut
        slug = slug[:max_length].rstrip("-")

    return slug


def format_html_text(text: str | None) -> str:
    """Render Markdown-style text (including links) as HTML using mistune."""

    if not text:
        return ""

    # Create a markdown parser with escaping enabled in the renderer
    # This prevents raw HTML tags from being passed through while
    # ensuring that markdown-generated HTML (like <code>) is NOT
    # double-escaped.
    renderer = mistune.HTMLRenderer(escape=True)
    markdown = mistune.create_markdown(renderer=renderer)

    result = markdown(text).strip()

    # If mistune wrapped it in <p>...</p> and it's a single paragraph,
    # we might want to strip it for inline use.
    if (
        result.startswith("<p>")
        and result.endswith("</p>")
        and result.count("<p>") == 1
    ):
        result = result[3:-4]

    return result


__all__ = [
    "slugify",
    "format_html_text",
]
