from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import html
import textwrap
import xml.etree.ElementTree as ET

from .entities import Citation, Insight, Section, ResearchTraceEvent
from .pdf import render_pdf_from_lines
from .text_utils import format_html_text, format_plain_text
from .xml_utils import etree_to_string


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
        overview_elem.text = format_plain_text(self.overview)

        if self.methodology:
            methodology_elem = ET.SubElement(root, "methodology")
            for step in self.methodology:
                ET.SubElement(methodology_elem, "step").text = (
                    format_plain_text(step)
                )

        if self.sections:
            sections_elem = ET.SubElement(root, "sections")
            for section in self.sections:
                sections_elem.append(section.to_xml())

        if self.open_questions:
            open_questions_elem = ET.SubElement(root, "open_questions")
            for question in self.open_questions:
                ET.SubElement(open_questions_elem, "question").text = (
                    format_plain_text(question)
                )

        if self.citations:
            citations_elem = ET.SubElement(root, "citations")
            for citation in self.citations:
                citations_elem.append(citation.to_xml())

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
            "    .insight-list { list-style: none; padding: 0; margin: 0; }",
            "    .insight-list > li { margin-bottom: 0.75rem; }",
            "    footer.site-footer {",
            "      padding: 1.5rem 8vw 2.5rem;",
            "      background: #0f172a;",
            "      color: #cbd5f5;",
            "      text-align: center;",
            "      font-size: 0.95rem;",
            "    }",
            "  </style>",
            "</head>",
            "<body>",
            "  <header class=\"site-header\">",
            f"    <h1>{topic_title}</h1>",
            f"    <p class=\"meta\">Generated at {generated_at}</p>",
            "  </header>",
            "  <main>",
        ]

        if self.overview:
            parts.append("    <section id=\"overview\">")
            parts.append("      <h2>Overview</h2>")
            overview_text = format_html_text(self.overview)
            parts.append(f"      <p>{overview_text}</p>")
            parts.append("    </section>")

        if self.methodology:
            parts.append(
                "    <section id=\"methodology\" "
                "aria-labelledby=\"methodology-title\">"
            )
            parts.append("      <h2 id=\"methodology-title\">Methodology</h2>")
            parts.append("      <ul>")
            for step in self.methodology:
                step_text = format_html_text(step)
                parts.append(f"        <li>{step_text}</li>")
            parts.append("      </ul>")
            parts.append("    </section>")

        if self.sections:
            parts.append(
                "    <section id=\"sections\" "
                "aria-labelledby=\"sections-title\">"
            )
            parts.append("      <h2 id=\"sections-title\">Sections</h2>")
            parts.append("      <div class=\"section-grid\">")
            for section in self.sections:
                section_id = html.escape(section.identifier)
                parts.append(
                    "        <article class=\"section-card\" "
                    f"id=\"{section_id}\">"
                )
                heading = format_html_text(section.title)
                parts.append(f"          <h3>{heading}</h3>")
                if section.summary:
                    summary_text = format_html_text(section.summary)
                    parts.append(f"          <p>{summary_text}</p>")
                if section.key_terms:
                    parts.append("          <h4>Key Terms</h4>")
                    parts.append("          <ul>")
                    for term in section.key_terms:
                        term_text = format_html_text(term)
                        parts.append(f"            <li>{term_text}</li>")
                    parts.append("          </ul>")
                if section.guiding_questions:
                    parts.append("          <h4>Guiding Questions</h4>")
                    parts.append("          <ul>")
                    for question in section.guiding_questions:
                        question_text = format_html_text(question)
                        parts.append(
                            f"            <li>{question_text}</li>"
                        )
                    parts.append("          </ul>")
                if section.insights:
                    parts.append("          <h4>Insights</h4>")
                    parts.append("          <ul class=\"insight-list\">")
                    for insight in section.insights:
                        insight_title = format_html_text(insight.title)
                        parts.append(
                            f"            <li><strong>{insight_title}</strong>"
                        )
                        parts.append("              <ul>")
                        evidence_text = format_html_text(insight.evidence)
                        parts.append(
                            "                <li>Evidence: "
                            f"{evidence_text}</li>"
                        )
                        if insight.implications:
                            implications_text = format_html_text(
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
                title = format_html_text(citation.title)
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
                    details.append(format_html_text(citation.summary))
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
                question_text = format_html_text(question)
                parts.append(f"        <li>{question_text}</li>")
            parts.append("      </ul>")
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
        return render_pdf_from_lines(lines)

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

        title_line = format_plain_text(self.topic)
        lines: list[str] = [title_line, "=" * len(title_line), ""]
        generated_text = self.generated_at.replace(
            microsecond=0
        ).isoformat()
        lines.append(f"Generated at: {generated_text}")
        lines.append("")

        if self.overview:
            lines.append("Overview:")
            lines.extend(wrapper.wrap(format_plain_text(self.overview)))
            lines.append("")

        if self.methodology:
            lines.append("Methodology:")
            for step in self.methodology:
                lines.extend(
                    wrap_text(format_plain_text(step), prefix="- ")
                )
            lines.append("")

        if self.sections:
            lines.append("Sections:")
            for section in self.sections:
                section_title = format_plain_text(section.title)
                heading = f"* {section_title}"
                if section.identifier:
                    heading += f" [{section.identifier}]"
                lines.append(heading)
                if section.summary:
                    lines.extend(
                        wrap_text(
                            format_plain_text(section.summary),
                            prefix="  ",
                        )
                    )
                if section.key_terms:
                    joined_terms = ", ".join(
                        format_plain_text(term)
                        for term in section.key_terms
                    )
                    lines.append(f"  Key terms: {joined_terms}")
                if section.guiding_questions:
                    lines.append("  Guiding questions:")
                    for question in section.guiding_questions:
                        lines.extend(
                            wrap_text(
                                format_plain_text(question),
                                prefix="    - ",
                            )
                        )
                if section.insights:
                    lines.append("  Insights:")
                    for insight in section.insights:
                        title_text = format_plain_text(insight.title)
                        lines.extend(
                            wrap_text(
                                title_text,
                                prefix="    * ",
                            )
                        )
                        evidence_text = format_plain_text(
                            insight.evidence
                        )
                        lines.extend(
                            wrap_text(
                                f"Evidence: {evidence_text}",
                                prefix="      ",
                            )
                        )
                        if insight.implications:
                            implication_text = format_plain_text(
                                insight.implications
                            )
                            lines.extend(
                                wrap_text(
                                    f"Implications: {implication_text}",
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
                title_text = format_plain_text(citation.title)
                header = f"- [{citation.identifier}] {title_text}"
                lines.append(header)
                lines.append(f"    URL: {citation.url}")
                if citation.publisher:
                    publisher_text = format_plain_text(citation.publisher)
                    lines.append(f"    Publisher: {publisher_text}")
                if citation.published_at:
                    lines.append(f"    Published: {citation.published_at}")
                if citation.summary:
                    summary_text = format_plain_text(citation.summary)
                    lines.extend(
                        wrap_text(
                            f"Summary: {summary_text}",
                            prefix="    ",
                        )
                    )
                lines.append("")

        if self.open_questions:
            lines.append("Open Questions:")
            for question in self.open_questions:
                lines.extend(
                    wrap_text(
                        format_plain_text(question),
                        prefix="- ",
                    )
                )
            lines.append("")

        if self.trace:
            lines.append("Trace:")
            for event in self.trace:
                lines.append(
                    f"- {event.event_type} [{event.status}] ({event.event_id})"
                )
            lines.append("")

        while lines and not lines[-1].strip():
            lines.pop()

        return lines

    @classmethod
    def from_payload(
        cls,
        topic: str,
        payload: dict[str, Any],
        generated_at: datetime | None = None,
    ) -> "Compendium":
        overview = payload.get("topic_overview") or ""
        methodology = [
            step.strip() for step in payload.get("methodology", []) if step
        ]

        sections_payload = payload.get("sections", [])
        sections: list[Section] = []
        for index, section in enumerate(sections_payload, start=1):
            identifier = section.get("id") or f"S{index:02d}"
            title = section.get("title") or "Untitled Section"
            summary = section.get("summary") or ""

            key_terms = [
                term.strip() for term in section.get("key_terms", []) if term
            ]
            guiding = [
                question.strip()
                for question in section.get("guiding_questions", [])
                if question
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


__all__ = ["Compendium"]
