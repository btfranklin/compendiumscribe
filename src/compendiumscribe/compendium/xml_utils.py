from __future__ import annotations

import xml.etree.ElementTree as ET


def etree_to_string(
    elem: ET.Element,
    cdata_tags: set[str] | None = None,
) -> str:
    """Serialize an element tree with indentation and preserved CDATA."""

    from xml.sax.saxutils import escape

    if cdata_tags is None:
        cdata_tags = set()

    def render_text(tag: str, text: str | None) -> str:
        if not text:
            return ""
        if tag in cdata_tags:
            return f"<![CDATA[{text}]]>"
        return escape(text)

    def serialize_element(e: ET.Element, depth: int = 0) -> str:
        indent = "  " * depth
        child_indent = "  " * (depth + 1)
        tag = e.tag
        attrib = " ".join(
            f'{k}="{escape(v)}"' for k, v in sorted(e.attrib.items())
        )
        attr_segment = f" {attrib}" if attrib else ""
        open_tag = f"{indent}<{tag}{attr_segment}>"
        close_tag = f"{indent}</{tag}>"

        children = list(e)
        text_content = render_text(tag, e.text)

        if not children:
            if text_content:
                return f"{open_tag}{text_content}</{tag}>\n"
            return f"{open_tag}{close_tag[len(indent):]}\n"

        parts: list[str] = [open_tag]
        if text_content:
            parts.append(text_content)
            parts.append("\n")
        else:
            parts.append("\n")

        for child in children:
            parts.append(serialize_element(child, depth + 1))
            tail_text = render_text(tag, child.tail)
            if tail_text:
                parts.append(f"{child_indent}{tail_text}\n")

        parts.append(f"{close_tag}\n")
        return "".join(parts)

    return serialize_element(elem).rstrip() + "\n"


__all__ = ["etree_to_string"]
