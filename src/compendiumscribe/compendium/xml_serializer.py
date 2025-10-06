from __future__ import annotations

from typing import TYPE_CHECKING
import xml.etree.ElementTree as ET

from .text_utils import format_plain_text
from .xml_utils import etree_to_string

if TYPE_CHECKING:  # pragma: no cover - hints only
    from .compendium import Compendium


_DEFAULT_CDATA_TAGS: set[str] = {
    "overview",
    "summary",
    "evidence",
    "implications",
    "step",
    "question",
    "title",
}


def build_xml_root(compendium: "Compendium") -> ET.Element:
    """Return an XML element representing the compendium."""

    root = ET.Element(
        "compendium",
        attrib={
            "topic": compendium.topic,
            "generated_at": compendium.generated_at.replace(
                microsecond=0
            ).isoformat(),
        },
    )

    overview_elem = ET.SubElement(root, "overview")
    overview_elem.text = format_plain_text(compendium.overview)

    if compendium.methodology:
        methodology_elem = ET.SubElement(root, "methodology")
        for step in compendium.methodology:
            ET.SubElement(methodology_elem, "step").text = (
                format_plain_text(step)
            )

    if compendium.sections:
        sections_elem = ET.SubElement(root, "sections")
        for section in compendium.sections:
            sections_elem.append(section.to_xml())

    if compendium.open_questions:
        questions_elem = ET.SubElement(root, "open_questions")
        for question in compendium.open_questions:
            ET.SubElement(questions_elem, "question").text = (
                format_plain_text(question)
            )

    if compendium.citations:
        citations_elem = ET.SubElement(root, "citations")
        for citation in compendium.citations:
            citations_elem.append(citation.to_xml())

    return root


def render_xml_string(
    compendium: "Compendium", *, cdata_tags: set[str] | None = None
) -> str:
    """Render the compendium to a UTF-8 XML string."""

    tags = cdata_tags or _DEFAULT_CDATA_TAGS
    return etree_to_string(build_xml_root(compendium), cdata_tags=tags)


__all__ = ["build_xml_root", "render_xml_string"]
