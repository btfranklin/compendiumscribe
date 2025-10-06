from __future__ import annotations

from typing import TYPE_CHECKING
import textwrap

from .text_utils import format_plain_text

if TYPE_CHECKING:  # pragma: no cover - hints only
    from .compendium import Compendium


def build_plain_text_lines(compendium: "Compendium") -> list[str]:
    """Produce a wrapped plain-text representation of the compendium."""

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

    title_line = format_plain_text(compendium.topic)
    lines: list[str] = [title_line, "=" * len(title_line), ""]
    generated_text = compendium.generated_at.replace(
        microsecond=0
    ).isoformat()
    lines.append(f"Generated at: {generated_text}")
    lines.append("")

    if compendium.overview:
        lines.append("Overview:")
        lines.extend(wrapper.wrap(format_plain_text(compendium.overview)))
        lines.append("")

    if compendium.methodology:
        lines.append("Methodology:")
        for step in compendium.methodology:
            lines.extend(
                wrap_text(format_plain_text(step), prefix="- ")
            )
        lines.append("")

    if compendium.sections:
        lines.append("Sections:")
        for section in compendium.sections:
            section_title = format_plain_text(section.title)
            heading = f"* {section_title}"
            if section.identifier:
                heading += f" ({section.identifier})"
            lines.append(heading)
            if section.summary:
                lines.extend(
                    wrap_text(
                        format_plain_text(section.summary),
                        prefix="  ",
                    )
                )
            if section.key_terms:
                lines.append("  Key Terms:")
                for term in section.key_terms:
                    lines.extend(
                        wrap_text(
                            format_plain_text(term),
                            prefix="  - ",
                        )
                    )
            if section.guiding_questions:
                lines.append("  Guiding Questions:")
                for question in section.guiding_questions:
                    lines.extend(
                        wrap_text(
                            format_plain_text(question),
                            prefix="  - ",
                        )
                    )
            if section.insights:
                lines.append("  Insights:")
                for insight in section.insights:
                    lines.append(
                        f"  - {format_plain_text(insight.title)}"
                    )
                    lines.extend(
                        wrap_text(
                            format_plain_text(insight.evidence),
                            prefix="    Evidence: ",
                        )
                    )
                    if insight.implications:
                        lines.extend(
                            wrap_text(
                                format_plain_text(insight.implications),
                                prefix="    Implications: ",
                            )
                        )
                    if insight.citation_refs:
                        refs = ", ".join(insight.citation_refs)
                        lines.append(f"    Citations: {refs}")
            lines.append("")

    if compendium.citations:
        lines.append("Citations:")
        for citation in compendium.citations:
            lines.append(
                f"- {format_plain_text(citation.title)} "
                f"[{citation.identifier}]"
            )
            if citation.url:
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

    if compendium.open_questions:
        lines.append("Open Questions:")
        for question in compendium.open_questions:
            lines.extend(
                wrap_text(
                    format_plain_text(question),
                    prefix="- ",
                )
            )
        lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()

    return lines


__all__ = ["build_plain_text_lines"]
