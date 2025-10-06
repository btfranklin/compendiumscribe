from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import html
import json
import textwrap
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

    def to_markdown(self) -> str:
        """Render the compendium as human-readable Markdown."""

        lines: list[str] = [f"# {self.topic}"]
        generated_label = self.generated_at.replace(
            microsecond=0
        ).isoformat()
        lines.append(f"_Generated at {generated_label}_")
        lines.append("")

        if self.overview:
            lines.append("## Overview")
            lines.append(self.overview)
            lines.append("")

        if self.methodology:
            lines.append("## Methodology")
            for step in self.methodology:
                lines.append(f"- {step}")
            lines.append("")

        if self.sections:
            lines.append("## Sections")
            lines.append("")
            for section in self.sections:
                heading = f"### {section.title}"
                if section.identifier:
                    heading += f" ({section.identifier})"
                lines.append(heading)
                if section.summary:
                    lines.append(section.summary)
                lines.append("")

                if section.key_terms:
                    lines.append("**Key Terms**")
                    for term in section.key_terms:
                        lines.append(f"- {term}")
                    lines.append("")

                if section.guiding_questions:
                    lines.append("**Guiding Questions**")
                    for question in section.guiding_questions:
                        lines.append(f"- {question}")
                    lines.append("")

                if section.insights:
                    lines.append("**Insights**")
                    for insight in section.insights:
                        lines.append(f"- **{insight.title}**")
                        lines.append(f"  - Evidence: {insight.evidence}")
                        if insight.implications:
                            lines.append(
                                f"  - Implications: {insight.implications}"
                            )
                        if insight.citation_refs:
                            refs = ", ".join(insight.citation_refs)
                            lines.append(f"  - Citations: {refs}")
                    lines.append("")

        if self.citations:
            lines.append("## Citations")
            for citation in self.citations:
                entry = (
                    f"- **[{citation.identifier}] {citation.title}** — "
                    f"{citation.url}"
                )
                details: list[str] = []
                if citation.publisher:
                    details.append(citation.publisher)
                if citation.published_at:
                    details.append(citation.published_at)
                if details:
                    entry += f" ({'; '.join(details)})"
                lines.append(entry)
                if citation.summary:
                    lines.append(f"  - Summary: {citation.summary}")
            lines.append("")

        if self.open_questions:
            lines.append("## Open Questions")
            for question in self.open_questions:
                lines.append(f"- {question}")
            lines.append("")

        if self.trace:
            lines.append("## Research Trace")
            for event in self.trace:
                description = (
                    f"- {event.event_type} ({event.status})"
                )
                if event.action:
                    action_json = json.dumps(event.action, ensure_ascii=False)
                    description += f" — {action_json}"
                lines.append(description)
            lines.append("")

        while lines and not lines[-1].strip():
            lines.pop()

        return "\n".join(lines) + "\n"

    def to_html(self) -> str:
        """Render the compendium as a simple styled HTML document."""

        topic_title = html.escape(self.topic)
        generated_at = html.escape(
            self.generated_at.replace(microsecond=0).isoformat()
        )

        parts = [
            "<!DOCTYPE html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\" />",
            "  <meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1\" />",
            f"  <title>{topic_title} Compendium</title>",
            "  <style>",
            (
                "    body { font-family: -apple-system, BlinkMacSystemFont, "
                "'Segoe UI', Arial, sans-serif; margin: 0; line-height: 1.6; }"
            ),
            "    main { display: block; padding: 2.5rem 8vw; }",
            "    header.site-header {",
            "      background: linear-gradient(135deg, #0f172a, #1d4ed8);",
            "      color: #f8fafc;",
            "      padding: 3rem 8vw 2.5rem;",
            "    }",
            "    header.site-header h1 {",
            "      font-size: clamp(2rem, 4vw, 3rem);",
            "      margin: 0;",
            "    }",
            "    header.site-header p {",
            "      margin: 0.75rem 0 0;",
            "      font-size: 1rem;",
            "    }",
            "    section { margin: 2.5rem 0; }",
            "    h2 { margin-bottom: 0.75rem; font-size: 1.6rem; }",
            "    h3 { margin-bottom: 0.25rem; font-size: 1.3rem; }",
            "    .meta { color: #94a3b8; font-size: 0.95rem; }",
            (
                "    .badge { font-size: 0.8rem; color: #555; margin-left: "
                "0.5rem; }"
            ),
            "    .section-grid { display: grid; gap: 1.5rem; }",
            "    article.section-card {",
            "      background: #0f172a0d;",
            "      border-radius: 0.75rem;",
            "      padding: 1.5rem;",
            "      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.1);",
            "    }",
            "    article.section-card header { margin-bottom: 0.75rem; }",
            "    ul, ol { padding-left: 1.2rem; }",
            "    .method-list { list-style: decimal; }",
            "    .insight-list > li { margin-bottom: 0.9rem; }",
            "    .citation-list { list-style: none; padding: 0; margin: 0; }",
            "    .citation-list li {",
            "      margin-bottom: 1rem;",
            "      background: #f8fafc;",
            "      border-radius: 0.5rem;",
            "      padding: 1rem;",
            "      box-shadow: inset 0 0 0 1px #e2e8f0;",
            "    }",
            "    .citation-meta { color: #475569; font-size: 0.95rem; }",
            "    table.trace-table {",
            "      border-collapse: collapse;",
            "      width: 100%;",
            "      border-radius: 0.5rem;",
            "      overflow: hidden;",
            "      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.1);",
            "    }",
            "    .trace-table caption {",
            "      text-align: left;",
            "      font-weight: 600;",
            "      padding: 0 0 0.75rem;",
            "    }",
            "    .trace-table th, .trace-table td {",
            "      padding: 0.75rem 1rem;",
            "      border-bottom: 1px solid #e2e8f0;",
            "      vertical-align: top;",
            "    }",
            "    .trace-table thead { background: #f1f5f9; }",
            "    footer.site-footer {",
            "      text-align: center;",
            "      padding: 2rem 8vw 3rem;",
            "      color: #64748b;",
            "      font-size: 0.9rem;",
            "    }",
            "    @media (max-width: 800px) {",
            "      main { padding: 2rem 1.5rem; }",
            "      table.trace-table { font-size: 0.9rem; }",
            "    }",
            "  </style>",
            "</head>",
            "<body>",
            "  <header class=\"site-header\">",
            f"    <h1>{topic_title}</h1>",
            (
                "    <p class=\"meta\">Generated "
                f"<time datetime=\"{generated_at}\">{generated_at}</time>"
                "</p>"
            ),
            "  </header>",
            "  <main>",
        ]

        if self.overview:
            parts.extend(
                [
                    (
                        "    <section id=\"overview\" "
                        "aria-labelledby=\"overview-title\">"
                    ),
                    "      <h2 id=\"overview-title\">Overview</h2>",
                    f"      <p>{html.escape(self.overview)}</p>",
                    "    </section>",
                ]
            )

        if self.methodology:
            parts.append(
                "    <section id=\"methodology\" "
                "aria-labelledby=\"methodology-title\">"
            )
            parts.append("      <h2 id=\"methodology-title\">Methodology</h2>")
            parts.append("      <ol class=\"method-list\">")
            for step in self.methodology:
                parts.append(f"        <li>{html.escape(step)}</li>")
            parts.append("      </ol>")
            parts.append("    </section>")

        if self.sections:
            parts.append(
                "    <section id=\"sections\" "
                "aria-labelledby=\"sections-title\">"
            )
            parts.append("      <h2 id=\"sections-title\">Sections</h2>")
            parts.append("      <div class=\"section-grid\">")
            for section in self.sections:
                title = html.escape(section.title)
                identifier = html.escape(section.identifier)
                parts.append("        <article class=\"section-card\">")
                parts.append("          <header>")
                header_text = f"{title}"
                if section.identifier:
                    header_text = (
                        f"{header_text} "
                        f"<span class=\"badge\">{identifier}</span>"
                    )
                parts.append(f"            <h3>{header_text}</h3>")
                parts.append("          </header>")
                if section.summary:
                    summary_text = html.escape(section.summary)
                    parts.append(f"          <p>{summary_text}</p>")
                if section.key_terms:
                    parts.append("          <h4>Key Terms</h4>")
                    parts.append("          <ul>")
                    for term in section.key_terms:
                        term_text = html.escape(term)
                        parts.append(f"            <li>{term_text}</li>")
                    parts.append("          </ul>")
                if section.guiding_questions:
                    parts.append("          <h4>Guiding Questions</h4>")
                    parts.append("          <ul>")
                    for question in section.guiding_questions:
                        question_text = html.escape(question)
                        parts.append(
                            f"            <li>{question_text}</li>"
                        )
                    parts.append("          </ul>")
                if section.insights:
                    parts.append("          <h4>Insights</h4>")
                    parts.append("          <ul class=\"insight-list\">")
                    for insight in section.insights:
                        insight_title = html.escape(insight.title)
                        parts.append(
                            f"            <li><strong>{insight_title}</strong>"
                        )
                        parts.append("              <ul>")
                        evidence_text = html.escape(insight.evidence)
                        parts.append(
                            "                <li>Evidence: "
                            f"{evidence_text}</li>"
                        )
                        if insight.implications:
                            implications_text = html.escape(
                                insight.implications
                            )
                            parts.append(
                                "                <li>Implications: "
                                f"{implications_text}</li>"
                            )
                        if insight.citation_refs:
                            refs = ", ".join(
                                html.escape(ref)
                                for ref in insight.citation_refs
                            )
                            parts.append(
                                "                <li>Citations: "
                                f"{refs}</li>"
                            )
                        parts.append("              </ul>")
                        parts.append("            </li>")
                    parts.append("          </ul>")
                parts.append("        </article>")
            parts.append("      </div>")
            parts.append("    </section>")

        if self.citations:
            parts.append(
                "    <section id=\"citations\" "
                "aria-labelledby=\"citations-title\">"
            )
            parts.append("      <h2 id=\"citations-title\">Citations</h2>")
            parts.append("      <ol class=\"citation-list\">")
            for citation in self.citations:
                title = html.escape(citation.title)
                identifier = html.escape(citation.identifier)
                url = html.escape(citation.url)
                parts.append("        <li>")
                parts.append("          <article>")
                parts.append(
                    "            <header>"
                    f"<h3>[{identifier}] {title}</h3>"
                    "</header>"
                )
                parts.append(
                    "            <p>"
                    f"<a href=\"{url}\" rel=\"noopener noreferrer\">{url}</a>"
                    "</p>"
                )
                details: list[str] = []
                if citation.publisher:
                    details.append(html.escape(citation.publisher))
                if citation.published_at:
                    details.append(html.escape(citation.published_at))
                if citation.summary:
                    details.append(html.escape(citation.summary))
                if details:
                    parts.append(
                        "            <p class=\"citation-meta\">"
                        f"{' · '.join(details)}"
                        "</p>"
                    )
                parts.append("          </article>")
                parts.append("        </li>")
            parts.append("      </ol>")
            parts.append("    </section>")

        if self.open_questions:
            parts.append(
                "    <section id=\"open-questions\" "
                "aria-labelledby=\"open-questions-title\">"
            )
            parts.append(
                "      <h2 id=\"open-questions-title\">Open Questions</h2>"
            )
            parts.append("      <ul>")
            for question in self.open_questions:
                parts.append(f"        <li>{html.escape(question)}</li>")
            parts.append("      </ul>")
            parts.append("    </section>")

        if self.trace:
            parts.append("    <section id=\"research-trace\">")
            parts.append(
                "      <table class=\"trace-table\">"
            )
            parts.append("        <caption>Research Trace</caption>")
            parts.append("        <thead>")
            parts.append("          <tr>")
            parts.append("            <th scope=\"col\">Event</th>")
            parts.append("            <th scope=\"col\">Status</th>")
            parts.append("            <th scope=\"col\">Action</th>")
            parts.append("          </tr>")
            parts.append("        </thead>")
            parts.append("        <tbody>")
            for event in self.trace:
                action = (
                    html.escape(json.dumps(event.action, ensure_ascii=False))
                    if event.action
                    else "—"
                )
                parts.append(
                    "          <tr>"
                    f"<td>{html.escape(event.event_type)}</td>"
                    f"<td>{html.escape(event.status)}</td>"
                    f"<td>{action}</td>"
                    "</tr>"
                )
            parts.append("        </tbody>")
            parts.append("      </table>")
            parts.append("    </section>")

        parts.append("  </main>")
        parts.append(
            "  <footer class=\"site-footer\">"
            "Generated by Compendium Scribe"
            "</footer>"
        )
        parts.append("</body>")
        parts.append("</html>")

        return "\n".join(parts) + "\n"

    def to_pdf_bytes(self) -> bytes:
        """Render the compendium as a lightweight PDF document."""

        lines = self._plain_text_lines()
        if not lines:
            lines = [""]
        return _render_pdf_from_lines(lines)

    def _plain_text_lines(self) -> list[str]:
        wrapper = textwrap.TextWrapper(width=80)

        def wrap_text(text: str, prefix: str = "") -> list[str]:
            if not text:
                return []
            local_wrapper = textwrap.TextWrapper(
                width=80,
                initial_indent=prefix,
                subsequent_indent="  " if prefix else "",
            )
            return local_wrapper.wrap(text)

        lines: list[str] = [self.topic, "=" * len(self.topic), ""]
        generated_text = self.generated_at.replace(
            microsecond=0
        ).isoformat()
        lines.append(f"Generated at: {generated_text}")
        lines.append("")

        if self.overview:
            lines.append("Overview:")
            lines.extend(wrapper.wrap(self.overview))
            lines.append("")

        if self.methodology:
            lines.append("Methodology:")
            for step in self.methodology:
                lines.extend(wrap_text(step, prefix="- "))
            lines.append("")

        if self.sections:
            lines.append("Sections:")
            for section in self.sections:
                heading = f"* {section.title}"
                if section.identifier:
                    heading += f" [{section.identifier}]"
                lines.append(heading)
                if section.summary:
                    lines.extend(wrap_text(section.summary, prefix="  "))
                if section.key_terms:
                    joined_terms = ", ".join(section.key_terms)
                    lines.append(f"  Key terms: {joined_terms}")
                if section.guiding_questions:
                    lines.append("  Guiding questions:")
                    for question in section.guiding_questions:
                        lines.extend(wrap_text(question, prefix="    - "))
                if section.insights:
                    lines.append("  Insights:")
                    for insight in section.insights:
                        lines.extend(wrap_text(insight.title, prefix="    * "))
                        lines.extend(
                            wrap_text(
                                f"Evidence: {insight.evidence}",
                                prefix="      ",
                            )
                        )
                        if insight.implications:
                            lines.extend(
                                wrap_text(
                                    f"Implications: {insight.implications}",
                                    prefix="      ",
                                )
                            )
                        if insight.citation_refs:
                            refs = ", ".join(insight.citation_refs)
                            lines.append(f"      Citations: {refs}")
                lines.append("")

        if self.citations:
            lines.append("Citations:")
            for citation in self.citations:
                header = f"- [{citation.identifier}] {citation.title}"
                lines.append(header)
                lines.append(f"    URL: {citation.url}")
                if citation.publisher:
                    lines.append(f"    Publisher: {citation.publisher}")
                if citation.published_at:
                    lines.append(
                        f"    Published: {citation.published_at}"
                    )
                if citation.summary:
                    lines.extend(
                        wrap_text(
                            f"Summary: {citation.summary}",
                            prefix="    ",
                        )
                    )
            lines.append("")

        if self.open_questions:
            lines.append("Open questions:")
            for question in self.open_questions:
                lines.extend(wrap_text(question, prefix="- "))
            lines.append("")

        if self.trace:
            lines.append("Research trace:")
            for event in self.trace:
                summary = f"- {event.event_type} ({event.status})"
                if event.action:
                    action_json = json.dumps(event.action, ensure_ascii=False)
                    summary += f" -> {action_json}"
                lines.append(summary)
            lines.append("")

        while lines and not lines[-1].strip():
            lines.pop()

        return [line.rstrip() for line in lines]

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


_PDF_PAGE_WIDTH = 612
_PDF_PAGE_HEIGHT = 792
_PDF_MARGIN = 72
_PDF_LINE_HEIGHT = 14


def _render_pdf_from_lines(lines: list[str]) -> bytes:
    lines_per_page = max(
        1,
        int((
            _PDF_PAGE_HEIGHT - 2 * _PDF_MARGIN
        ) // _PDF_LINE_HEIGHT),
    )
    if not lines:
        lines = [""]

    pages: list[list[str]] = []
    for index in range(0, len(lines), lines_per_page):
        pages.append(lines[index:index + lines_per_page])
    if not pages:
        pages = [[""]]

    page_streams = [_build_pdf_stream(page) for page in pages]
    return _assemble_pdf_document(page_streams)


def _build_pdf_stream(lines: list[str]) -> str:
    if not lines:
        lines = [""]

    stream_lines = [
        "BT",
        "/F1 12 Tf",
        f"{_PDF_LINE_HEIGHT} TL",
        f"1 0 0 1 {_PDF_MARGIN} {_PDF_PAGE_HEIGHT - _PDF_MARGIN} Tm",
    ]

    for line in lines:
        sanitized = _pdf_escape_text(line)
        stream_lines.append(f"({sanitized}) Tj")
        stream_lines.append("T*")

    stream_lines.append("ET")
    return "\n".join(stream_lines)


def _pdf_escape_text(text: str) -> str:
    safe_text = text.encode("latin-1", "replace").decode("latin-1")
    safe_text = safe_text.replace("\\", "\\\\")
    safe_text = safe_text.replace("(", "\\(")
    safe_text = safe_text.replace(")", "\\)")
    return safe_text


def _assemble_pdf_document(page_streams: list[str]) -> bytes:
    if not page_streams:
        page_streams = [_build_pdf_stream([""])]

    num_pages = len(page_streams)
    page_ids = [4 + index for index in range(num_pages)]
    content_ids = [4 + num_pages + index for index in range(num_pages)]

    objects: dict[int, str] = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    kids_entries = " ".join(f"{page_id} 0 R" for page_id in page_ids) or ""
    objects[2] = (
        "<< /Type /Pages /Kids ["
        f"{kids_entries}"
        "] /Count "
        f"{num_pages} >>"
    )

    for index, page_id in enumerate(page_ids):
        content_id = content_ids[index]
        page_dict = (
            "<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {_PDF_PAGE_WIDTH} {_PDF_PAGE_HEIGHT}] "
            "/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        objects[page_id] = page_dict

        stream = page_streams[index]
        stream_bytes = stream.encode("latin-1")
        content_object = (
            f"<< /Length {len(stream_bytes)} >>\n"
            f"stream\n{stream}\nendstream"
        )
        objects[content_id] = content_object

    max_object_id = max(objects)

    pdf_parts: list[str] = ["%PDF-1.4\n"]
    offsets: dict[int, int] = {}
    current_offset = len(pdf_parts[0].encode("latin-1"))

    for object_id in range(1, max_object_id + 1):
        content = objects.get(object_id)
        if content is None:
            continue
        serialized = f"{object_id} 0 obj\n{content}\nendobj\n"
        offsets[object_id] = current_offset
        encoded = serialized.encode("latin-1")
        pdf_parts.append(serialized)
        current_offset += len(encoded)

    xref_start = current_offset

    total_objects = max_object_id
    xref_lines = [
        "xref",
        f"0 {total_objects + 1}",
        "0000000000 65535 f ",
    ]
    for object_id in range(1, total_objects + 1):
        offset = offsets.get(object_id, 0)
        xref_lines.append(f"{offset:010} 00000 n ")

    xref_text = "\n".join(xref_lines) + "\n"
    pdf_parts.append(xref_text)
    current_offset += len(xref_text.encode("latin-1"))

    trailer = (
        "trailer\n"
        f"<< /Size {total_objects + 1} /Root 1 0 R >>\n"
        "startxref\n"
        f"{xref_start}\n"
        "%%EOF\n"
    )
    pdf_parts.append(trailer)

    return "".join(pdf_parts).encode("latin-1")
