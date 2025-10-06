from __future__ import annotations

from typing import TYPE_CHECKING
import html

from .text_utils import format_html_text

if TYPE_CHECKING:  # pragma: no cover - hints only
    from .compendium import Compendium


def render_html(compendium: "Compendium") -> str:
    """Render the compendium as a styled HTML document."""

    topic_title = html.escape(compendium.topic)
    generated_at = html.escape(
        compendium.generated_at.replace(microsecond=0).isoformat()
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

    if compendium.overview:
        parts.append("    <section id=\"overview\">")
        parts.append("      <h2>Overview</h2>")
        overview_text = format_html_text(compendium.overview)
        parts.append(f"      <p>{overview_text}</p>")
        parts.append("    </section>")

    if compendium.methodology:
        parts.append(
            "    <section id=\"methodology\" "
            "aria-labelledby=\"methodology-title\">"
        )
        parts.append("      <h2 id=\"methodology-title\">Methodology</h2>")
        parts.append("      <ul>")
        for step in compendium.methodology:
            step_text = format_html_text(step)
            parts.append(f"        <li>{step_text}</li>")
        parts.append("      </ul>")
        parts.append("    </section>")

    if compendium.sections:
        parts.append(
            "    <section id=\"sections\" "
            "aria-labelledby=\"sections-title\">"
        )
        parts.append("      <h2 id=\"sections-title\">Sections</h2>")
        parts.append("      <div class=\"section-grid\">")
        for section in compendium.sections:
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
                    parts.append(f"            <li>{question_text}</li>")
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

    if compendium.citations:
        parts.append(
            "    <section id=\"citations\" "
            "aria-labelledby=\"citations-title\">"
        )
        parts.append("      <h2 id=\"citations-title\">Citations</h2>")
        parts.append("      <ol class=\"citation-list\">")
        for citation in compendium.citations:
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

    if compendium.open_questions:
        parts.append(
            "    <section id=\"open-questions\" "
            "aria-labelledby=\"open-questions-title\">"
        )
        parts.append(
            "      <h2 id=\"open-questions-title\">Open Questions</h2>"
        )
        parts.append("      <ul>")
        for question in compendium.open_questions:
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


__all__ = ["render_html"]
