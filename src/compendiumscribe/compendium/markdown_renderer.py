from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - hints only
    from .compendium import Compendium


def render_markdown(compendium: "Compendium") -> str:
    """Render the compendium as a human-readable Markdown document."""

    lines: list[str] = [f"# {compendium.topic}"]
    generated_label = compendium.generated_at.replace(
        microsecond=0
    ).isoformat()
    lines.append(f"_Generated at {generated_label}_")
    lines.append("")

    if compendium.overview:
        lines.append("## Overview")
        lines.append(compendium.overview)
        lines.append("")

    if compendium.methodology:
        lines.append("## Methodology")
        for step in compendium.methodology:
            lines.append(f"- {step}")
        lines.append("")

    if compendium.sections:
        lines.append("## Sections")
        lines.append("")
        for section in compendium.sections:
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

    if compendium.citations:
        lines.append("## Citations")
        for citation in compendium.citations:
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

    if compendium.open_questions:
        lines.append("## Open Questions")
        for question in compendium.open_questions:
            lines.append(f"- {question}")
        lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines) + "\n"


__all__ = ["render_markdown"]
