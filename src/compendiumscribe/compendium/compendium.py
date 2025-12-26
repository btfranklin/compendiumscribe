from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import xml.etree.ElementTree as ET

from .entities import Citation, Section
from .html_site_renderer import render_html_site
from .markdown_renderer import render_markdown
from .payload_parser import build_from_payload
from .xml_utils import etree_to_string


@dataclass
class Compendium:
    """Structured representation of a research compendium."""

    XML_CDATA_TAGS = {
        "overview",
        "summary",
        "evidence",
        "implications",
        "step",
        "question",
        "title",
    }

    topic: str
    overview: str
    methodology: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_xml(self) -> ET.Element:
        """Return an XML element representing the compendium."""
        root = ET.Element(
            "compendium",
            attrib={
                "topic": self.topic,
                "generated_at": self.generated_at.replace(
                    microsecond=0
                ).isoformat(),
            },
        )

        overview_elem = ET.SubElement(root, "overview")
        overview_elem.text = self.overview

        if self.methodology:
            methodology_elem = ET.SubElement(root, "methodology")
            for step in self.methodology:
                ET.SubElement(methodology_elem, "step").text = step

        if self.sections:
            sections_elem = ET.SubElement(root, "sections")
            for section in self.sections:
                sections_elem.append(section.to_xml())

        if self.open_questions:
            questions_elem = ET.SubElement(root, "open_questions")
            for question in self.open_questions:
                ET.SubElement(questions_elem, "question").text = question

        if self.citations:
            citations_elem = ET.SubElement(root, "citations")
            for citation in self.citations:
                citations_elem.append(citation.to_xml())

        return root

    def to_xml_string(self) -> str:
        """Render the compendium to a UTF-8 XML string with CDATA wrapping."""
        return etree_to_string(self.to_xml(), cdata_tags=self.XML_CDATA_TAGS)

    def to_markdown(self) -> str:
        """Render the compendium as human-readable Markdown."""

        return render_markdown(self)

    def to_html_site(self) -> dict[str, str]:
        """Render the compendium as a navigable multi-file HTML site.

        Returns a dictionary mapping relative file paths to their content.
        """

        return render_html_site(self)

    def to_pdf_bytes(self) -> bytes:
        """Render the compendium as a professional PDF document."""
        from .pdf import render_pdf

        return render_pdf(self)

    @classmethod
    def from_payload(
        cls,
        topic: str,
        payload: dict[str, Any],
        generated_at: datetime | None = None,
    ) -> "Compendium":
        return build_from_payload(
            cls,
            topic=topic,
            payload=payload,
            generated_at=generated_at,
        )

    @classmethod
    def from_xml_file(cls, path: str) -> "Compendium":
        """Load a compendium from an XML file."""
        from .xml_parser import parse_xml_file

        return parse_xml_file(path)

    @classmethod
    def from_xml_string(cls, content: str) -> "Compendium":
        """Load a compendium from an XML string."""
        from .xml_parser import parse_xml_string

        return parse_xml_string(content)


__all__ = ["Compendium"]
