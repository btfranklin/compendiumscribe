from __future__ import annotations

from .compendium import (
    Citation,
    Compendium,
    Insight,
    ResearchTraceEvent,
    Section,
    etree_to_string,
    format_html_text,
    format_plain_text,
    iter_markdown_links,
    render_pdf_from_lines,
)

# Backwards-compatible aliases for prior private helpers
_iter_markdown_links = iter_markdown_links
_format_plain_text = format_plain_text
_format_html_text = format_html_text
_render_pdf_from_lines = render_pdf_from_lines

__all__ = [
    "Citation",
    "Compendium",
    "Insight",
    "ResearchTraceEvent",
    "Section",
    "etree_to_string",
    "format_html_text",
    "format_plain_text",
    "iter_markdown_links",
    "render_pdf_from_lines",
]
