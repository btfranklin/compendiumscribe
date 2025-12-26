from __future__ import annotations

from typing import Iterator
import html
import mistune


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "page"




def format_html_text(text: str | None) -> str:
    """Render Markdown-style text (including links) as HTML using mistune."""

    if not text:
        return ""

    # Create a markdown parser with escaping enabled in the renderer
    # This prevents raw HTML tags from being passed through while 
    # ensuring that markdown-generated HTML (like <code>) is NOT double-escaped.
    renderer = mistune.HTMLRenderer(escape=True)
    markdown = mistune.create_markdown(renderer=renderer)
    
    result = markdown(text).strip()
    
    # If mistune wrapped it in <p>...</p> and it's a single paragraph, 
    # we might want to strip it for inline use.
    if result.startswith("<p>") and result.endswith("</p>") and result.count("<p>") == 1:
        result = result[3:-4]
        
    return result


__all__ = [
    "slugify",
    "format_html_text",
]
