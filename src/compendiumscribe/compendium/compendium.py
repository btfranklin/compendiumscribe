from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import xml.etree.ElementTree as ET

from .entities import Citation, Section
from .html_renderer import render_html
from .html_site_renderer import render_html_site
from .markdown_renderer import render_markdown
from .payload_parser import build_from_payload
from .plain_text import build_plain_text_lines
from .pdf import render_pdf_from_lines
from .payload_parser import build_from_payload
from .plain_text import build_plain_text_lines
from .pdf import render_pdf_from_lines
from .xml_serializer import build_xml_root, render_xml_string


@dataclass
class Compendium:
    """Structured representation of a research compendium."""

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
        return build_xml_root(self)

    def to_xml_string(self) -> str:
        return render_xml_string(self)

    def to_markdown(self) -> str:
        """Render the compendium as human-readable Markdown."""

        return render_markdown(self)

    def to_html(self) -> str:
        """Render the compendium as a simple styled HTML document."""

        return render_html(self)

    def to_html_site(self) -> dict[str, str]:
        """Render the compendium as a navigable multi-file HTML site.

        Returns a dictionary mapping relative file paths to their content.
        """

        return render_html_site(self)

    def to_pdf_bytes(self) -> bytes:
        """Render the compendium as a lightweight PDF document."""

        lines = self._plain_text_lines()
        if not lines:
            lines = [""]
        return render_pdf_from_lines(lines)

    def _plain_text_lines(self) -> list[str]:
        return build_plain_text_lines(self)

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
