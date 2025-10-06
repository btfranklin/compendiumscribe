from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json
import xml.etree.ElementTree as ET

from .text_utils import format_plain_text


@dataclass
class Citation:
    """Represents a single cited source returned by deep research."""

    identifier: str
    title: str
    url: str
    publisher: str | None = None
    published_at: str | None = None
    summary: str | None = None

    def to_xml(self) -> ET.Element:
        citation_elem = ET.Element("citation", attrib={"id": self.identifier})

        ET.SubElement(citation_elem, "title").text = format_plain_text(
            self.title
        )
        ET.SubElement(citation_elem, "url").text = self.url

        if self.publisher:
            publisher_elem = ET.SubElement(citation_elem, "publisher")
            publisher_elem.text = format_plain_text(self.publisher)
        if self.published_at:
            published_elem = ET.SubElement(citation_elem, "published_at")
            published_elem.text = self.published_at
        if self.summary:
            summary_elem = ET.SubElement(citation_elem, "summary")
            summary_elem.text = format_plain_text(self.summary)

        return citation_elem


@dataclass
class Insight:
    """Represents a targeted piece of analysis within a section."""

    title: str
    evidence: str
    implications: str | None = None
    citation_refs: list[str] = field(default_factory=list)

    def to_xml(self) -> ET.Element:
        insight_elem = ET.Element("insight")
        ET.SubElement(insight_elem, "title").text = format_plain_text(
            self.title
        )

        evidence_elem = ET.SubElement(insight_elem, "evidence")
        evidence_elem.text = format_plain_text(self.evidence)

        if self.implications:
            implications_elem = ET.SubElement(insight_elem, "implications")
            implications_elem.text = format_plain_text(self.implications)

        if self.citation_refs:
            citations_elem = ET.SubElement(insight_elem, "citations")
            for ref in self.citation_refs:
                ET.SubElement(citations_elem, "ref").text = ref

        return insight_elem


@dataclass
class Section:
    """Organises a slice of the compendium into a structured section."""

    identifier: str
    title: str
    summary: str
    key_terms: list[str] = field(default_factory=list)
    guiding_questions: list[str] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)

    def to_xml(self) -> ET.Element:
        section_elem = ET.Element("section", attrib={"id": self.identifier})
        ET.SubElement(section_elem, "title").text = format_plain_text(
            self.title
        )

        summary_elem = ET.SubElement(section_elem, "summary")
        summary_elem.text = format_plain_text(self.summary)

        if self.key_terms:
            key_terms_elem = ET.SubElement(
                section_elem,
                "key_terms",
            )
            for term in self.key_terms:
                term_elem = ET.SubElement(key_terms_elem, "term")
                term_elem.text = format_plain_text(term)

        if self.guiding_questions:
            questions_elem = ET.SubElement(section_elem, "guiding_questions")
            for question in self.guiding_questions:
                ET.SubElement(questions_elem, "question").text = (
                    format_plain_text(question)
                )

        if self.insights:
            insights_elem = ET.SubElement(section_elem, "insights")
            for insight in self.insights:
                insights_elem.append(insight.to_xml())

        return section_elem


@dataclass
class ResearchTraceEvent:
    """Captures tool calls emitted by deep research for auditing purposes."""

    event_id: str
    event_type: str
    status: str
    action: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] | None = None

    def to_xml(self) -> ET.Element:
        event_elem = ET.Element(
            "trace_event",
            attrib={
                "id": self.event_id,
                "type": self.event_type,
                "status": self.status,
            },
        )

        if self.action:
            action_elem = ET.SubElement(event_elem, "action")
            action_elem.text = json.dumps(self.action, ensure_ascii=False)

        if self.response:
            response_elem = ET.SubElement(event_elem, "result")
            response_elem.text = json.dumps(self.response, ensure_ascii=False)

        return event_elem


__all__ = [
    "Citation",
    "Insight",
    "Section",
    "ResearchTraceEvent",
]
