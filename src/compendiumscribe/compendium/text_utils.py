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


def process_italic(text: str) -> str:
    """Wrap *text* in <em> tags."""
    # Split by *
    parts_star = text.split("*")
    processed_parts: list[str] = []
    
    for i, part in enumerate(parts_star):
        if i % 2 == 1:
            # Odd segments inside *
            processed_parts.append(f"<em>{html.escape(part)}</em>")
        else:
            # Even segments outside *, handle _ next
            sub_parts = part.split("_")
            for j, sub in enumerate(sub_parts):
                if j % 2 == 1:
                    sub_parts[j] = f"<em>{html.escape(sub)}</em>"
                else:
                    sub_parts[j] = html.escape(sub)
            processed_parts.append("".join(sub_parts))
            
    return "".join(processed_parts)


def process_bold(text: str) -> str:
    """Wrap **text** or __text__ in <strong> tags."""
    # Split by ** first
    parts = text.split("**")
    processed_parts: list[str] = []
    
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Odd segments inside **
            # Recurse for italics inside bold
            processed_parts.append(f"<strong>{process_italic(part)}</strong>")
        else:
            # Even segments outside **, handle __ next
            # Note: __ splits
            sub_parts = part.split("__")
            for j, sub in enumerate(sub_parts):
                if j % 2 == 1:
                    sub_parts[j] = f"<strong>{process_italic(sub)}</strong>"
                else:
                    sub_parts[j] = process_italic(sub)
            processed_parts.append("".join(sub_parts))
    
    return "".join(processed_parts)


def process_inline_markdown(text: str) -> str:
    """Escape text for HTML and wrap inline markdown (code, bold, italic)."""
    parts = text.split("`")
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Odd segments are inside backticks: escaping only
            parts[i] = f"<code>{html.escape(part)}</code>"
        else:
            # Even segments are outside backticks: process bold/italic
            parts[i] = process_bold(part)
    return "".join(parts)


def format_html_text(text: str | None) -> str:
    """Render Markdown-style links and inline formatting as HTML."""

    if text is None:
        return ""
    if text == "":
        return ""

    parts: list[str] = []
    cursor = 0
    for start, end, label, url in iter_markdown_links(text):
        # Process text before the link
        parts.append(process_inline_markdown(text[cursor:start]))
        
        clean_url = url.strip()
        # Process markdown inside the link label
        processed_label = process_inline_markdown(label)
        
        if clean_url:
            escaped_url = html.escape(clean_url, quote=True)
            anchor = (
                f"<a href=\"{escaped_url}\" "
                f"rel=\"noopener noreferrer\">{processed_label}</a>"
            )
            parts.append(anchor)
        else:
            parts.append(processed_label)
        cursor = end

    # Process remaining text
    parts.append(process_inline_markdown(text[cursor:]))
    return "".join(parts)


__all__ = [
    "iter_markdown_links",
    "format_plain_text",
    "format_html_text",
]
