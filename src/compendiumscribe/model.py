from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json
import xml.etree.ElementTree as ET


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

        ET.SubElement(citation_elem, "title").text = self.title
        ET.SubElement(citation_elem, "url").text = self.url

        if self.publisher:
            publisher_elem = ET.SubElement(citation_elem, "publisher")
            publisher_elem.text = self.publisher
        if self.published_at:
            published_elem = ET.SubElement(citation_elem, "published_at")
            published_elem.text = self.published_at
        if self.summary:
            summary_elem = ET.SubElement(citation_elem, "summary")
            summary_elem.text = self.summary

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
        ET.SubElement(insight_elem, "title").text = self.title

        evidence_elem = ET.SubElement(insight_elem, "evidence")
        evidence_elem.text = self.evidence

        if self.implications:
            implications_elem = ET.SubElement(insight_elem, "implications")
            implications_elem.text = self.implications

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
        ET.SubElement(section_elem, "title").text = self.title

        summary_elem = ET.SubElement(section_elem, "summary")
        summary_elem.text = self.summary

        if self.key_terms:
            key_terms_elem = ET.SubElement(section_elem, "key_terms")
            for term in self.key_terms:
                ET.SubElement(key_terms_elem, "term").text = term

        if self.guiding_questions:
            questions_elem = ET.SubElement(section_elem, "guiding_questions")
            for question in self.guiding_questions:
                ET.SubElement(questions_elem, "question").text = question

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


@dataclass
class Compendium:
    """Structured representation of a research compendium."""

    topic: str
    overview: str
    methodology: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    trace: list[ResearchTraceEvent] = field(default_factory=list)
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_xml(self) -> ET.Element:
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
            open_questions_elem = ET.SubElement(root, "open_questions")
            for question in self.open_questions:
                ET.SubElement(open_questions_elem, "question").text = question

        if self.citations:
            citations_elem = ET.SubElement(root, "citations")
            for citation in self.citations:
                citations_elem.append(citation.to_xml())

        if self.trace:
            trace_elem = ET.SubElement(root, "research_trace")
            for event in self.trace:
                trace_elem.append(event.to_xml())

        return root

    def to_xml_string(self) -> str:
        cdata_tags = {
            "overview",
            "summary",
            "evidence",
            "implications",
            "step",
            "question",
            "title",
        }
        return etree_to_string(self.to_xml(), cdata_tags=cdata_tags)

    @classmethod
    def from_payload(
        cls,
        topic: str,
        payload: dict[str, Any],
        *,
        generated_at: datetime | None = None,
    ) -> "Compendium":
        """Build a compendium from the deep research JSON payload."""

        overview = payload.get("topic_overview", "").strip()
        methodology = [
            step.strip()
            for step in payload.get("methodology", [])
            if step
        ]

        sections_data = payload.get("sections", [])
        sections: list[Section] = []
        for index, section in enumerate(sections_data, start=1):
            identifier = section.get("id") or f"S{index:02d}"
            title = section.get("title", "Untitled Section").strip()
            summary = section.get("summary", "").strip()
            key_terms = [
                term.strip() for term in section.get("key_terms", []) if term
            ]
            guiding = [
                q.strip()
                for q in section.get("guiding_questions", [])
                if q
            ]
            insights_payload = section.get("insights", [])

            insights: list[Insight] = []
            for insight in insights_payload:
                implications_text = (
                    (insight.get("implications") or "").strip() or None
                )
                insights.append(
                    Insight(
                        title=(insight.get("title") or "Key Insight").strip(),
                        evidence=(insight.get("evidence") or "").strip(),
                        implications=implications_text,
                        citation_refs=[
                            ref.strip()
                            for ref in insight.get("citations", [])
                            if ref
                        ],
                    )
                )

            sections.append(
                Section(
                    identifier=identifier,
                    title=title,
                    summary=summary,
                    key_terms=key_terms,
                    guiding_questions=guiding,
                    insights=insights,
                )
            )

        citations_payload = payload.get("citations", [])
        citations: list[Citation] = []
        for index, citation in enumerate(citations_payload, start=1):
            identifier = citation.get("id") or f"C{index:02d}"
            citations.append(
                Citation(
                    identifier=identifier,
                    title=citation.get("title", "Untitled Source").strip(),
                    url=citation.get("url", "").strip(),
                    publisher=(
                        (citation.get("publisher") or "").strip() or None
                    ),
                    published_at=(
                        (citation.get("published_at") or "").strip() or None
                    ),
                    summary=(
                        (citation.get("summary") or "").strip() or None
                    ),
                )
            )

        open_questions = [
            q.strip() for q in payload.get("open_questions", []) if q
        ]

        trace_payload = payload.get("trace", [])
        trace: list[ResearchTraceEvent] = []
        for event in trace_payload:
            event_id = str(event.get("id", "")) or f"event-{len(trace) + 1}"
            trace.append(
                ResearchTraceEvent(
                    event_id=event_id,
                    event_type=str(event.get("type", "message")),
                    status=str(event.get("status", "unknown")),
                    action=event.get("action", {}) or {},
                    response=event.get("response") or None,
                )
            )

        return cls(
            topic=topic,
            overview=overview,
            methodology=methodology,
            sections=sections,
            citations=citations,
            open_questions=open_questions,
            trace=trace,
            generated_at=generated_at or datetime.now(timezone.utc),
        )


def etree_to_string(
    elem: ET.Element,
    cdata_tags: set[str] | None = None,
) -> str:
    """Serialize an element tree to a string while preserving CDATA tags."""

    from xml.sax.saxutils import escape

    if cdata_tags is None:
        cdata_tags = set()

    def serialize_element(e: ET.Element) -> str:
        tag = e.tag
        attrib = " ".join(
            f'{k}="{escape(v)}"' for k, v in e.attrib.items()
        )
        attr_segment = f" {attrib}" if attrib else ""
        open_tag = f"<{tag}{attr_segment}>"
        close_tag = f"</{tag}>"

        parts = [open_tag]

        if e.text:
            if tag in cdata_tags:
                parts.append(f"<![CDATA[{e.text}]]>")
            else:
                parts.append(escape(e.text))

        for child in e:
            parts.append(serialize_element(child))
            if child.tail:
                parts.append(escape(child.tail))

        parts.append(close_tag)
        return "".join(parts)

    return serialize_element(elem)
