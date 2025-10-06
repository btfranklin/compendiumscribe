from __future__ import annotations

from typing import Iterator
import html


def iter_markdown_links(text: str) -> Iterator[tuple[int, int, str, str]]:
    """Yield ranges and components for Markdown-style inline links."""

    index = 0
    length = len(text)
    while index < length:
        start = text.find("[", index)
        if start == -1:
            break

        end_label = text.find("]", start + 1)
        if end_label == -1:
            break
        if end_label + 1 >= length or text[end_label + 1] != "(":
            index = end_label + 1
            continue

        url_start = end_label + 2
        depth = 1
        position = url_start
        while position < length and depth > 0:
            char = text[position]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            position += 1

        if depth != 0:
            break

        url_end = position
        label = text[start + 1:end_label]
        url = text[url_start:url_end]
        yield start, url_end + 1, label, url
        index = url_end + 1


def format_plain_text(text: str) -> str:
    """Replace Markdown-style links with plain text equivalents."""

    if not text:
        return text

    segments: list[str] = []
    cursor = 0
    transformed = False
    for start, end, label, url in iter_markdown_links(text):
        segments.append(text[cursor:start])
        clean_url = url.strip()
        replacement = f"{label} ({clean_url})" if clean_url else label
        segments.append(replacement)
        cursor = end
        transformed = True

    if not transformed:
        return text

    segments.append(text[cursor:])
    return "".join(segments)


def format_html_text(text: str | None) -> str:
    """Render Markdown-style links as HTML anchors while escaping content."""

    if text is None:
        return ""
    if text == "":
        return ""

    parts: list[str] = []
    cursor = 0
    for start, end, label, url in iter_markdown_links(text):
        parts.append(html.escape(text[cursor:start]))
        clean_url = url.strip()
        escaped_label = html.escape(label)
        if clean_url:
            escaped_url = html.escape(clean_url, quote=True)
            anchor = (
                f"<a href=\"{escaped_url}\" "
                f"rel=\"noopener noreferrer\">{escaped_label}</a>"
            )
            parts.append(anchor)
        else:
            parts.append(escaped_label)
        cursor = end

    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


__all__ = [
    "iter_markdown_links",
    "format_plain_text",
    "format_html_text",
]
