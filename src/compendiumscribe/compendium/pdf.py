from __future__ import annotations

from typing import TYPE_CHECKING
from fpdf import FPDF
from fpdf.enums import XPos, YPos

if TYPE_CHECKING:
    from .compendium import Compendium


class CompendiumPDF(FPDF):
    def header(self):
        # We don't need a default header for every page yet
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def render_pdf(compendium: Compendium) -> bytes:
    """Render a professional PDF document from a Compendium object."""

    pdf = CompendiumPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    # Title
    pdf.set_font("helvetica", "B", 24)
    pdf.cell(
        0,
        20,
        compendium.topic,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="C",
    )

    pdf.set_font("helvetica", "I", 10)
    generated_at = compendium.generated_at.strftime("%Y-%m-%d %H:%M:%S")
    pdf.cell(
        0,
        10,
        f"Generated at: {generated_at} UTC",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="C",
    )
    pdf.ln(10)

    # Overview
    if compendium.overview:
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, "Overview", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("helvetica", "", 11)
        pdf.multi_cell(0, 6, compendium.overview)
        pdf.ln(5)

    # Methodology
    if compendium.methodology:
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(
            0,
            10,
            "Methodology",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font("helvetica", "", 11)
        for step in compendium.methodology:
            if step.strip():
                pdf.multi_cell(
                    0,
                    6,
                    f"- {step}",
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )
        pdf.ln(5)

    # Sections
    if compendium.sections:
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(
            0,
            10,
            "Sections",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(2)

        for section in compendium.sections:
            # Check for page break if near bottom
            if pdf.get_y() > 250:
                pdf.add_page()

            pdf.set_font("helvetica", "B", 14)
            title = section.title
            if section.identifier:
                title = f"{section.identifier}: {title}"
            pdf.cell(
                0,
                10,
                title,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

            pdf.set_font("helvetica", "", 11)
            pdf.multi_cell(0, 6, section.summary)
            pdf.ln(2)

            if section.key_terms:
                pdf.set_font("helvetica", "B", 10)
                pdf.cell(0, 6, "Key Terms: ", ln=False)
                pdf.set_font("helvetica", "", 10)
                pdf.multi_cell(0, 6, ", ".join(section.key_terms))

            if section.insights:
                pdf.ln(2)
                for insight in section.insights:
                    pdf.set_font("helvetica", "B", 11)
                    pdf.cell(
                        0,
                        8,
                        f"Insight: {insight.title}",
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )
                    pdf.set_font("helvetica", "", 11)
                    pdf.multi_cell(0, 6, insight.evidence)
                    if insight.implications:
                        pdf.set_font("helvetica", "I", 11)
                        pdf.multi_cell(
                            0,
                            6,
                            f"Implications: {insight.implications}",
                        )
                    if insight.citation_refs:
                        pdf.set_font("helvetica", "", 9)
                        pdf.cell(
                            0,
                            6,
                            f"Citations: {', '.join(insight.citation_refs)}",
                            new_x=XPos.LMARGIN,
                            new_y=YPos.NEXT,
                        )
                    pdf.ln(2)
            pdf.ln(5)

    # Citations
    if compendium.citations:
        if pdf.get_y() > 220:
            pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(
            0,
            10,
            "Citations",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font("helvetica", "", 10)
        for citation in compendium.citations:
            pdf.set_font("helvetica", "B", 10)
            label = f"[{citation.identifier}] {citation.title}"
            pdf.multi_cell(0, 6, label)
            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(0, 0, 255)
            pdf.cell(
                0,
                6,
                citation.url,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
                link=citation.url,
            )
            pdf.set_text_color(0, 0, 0)
            if citation.summary:
                pdf.multi_cell(0, 6, citation.summary)
            pdf.ln(2)

    # Open Questions
    if compendium.open_questions:
        if pdf.get_y() > 220:
            pdf.add_page()
        pdf.ln(5)
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(
            0,
            10,
            "Open Questions",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font("helvetica", "", 11)
        for question in compendium.open_questions:
            pdf.multi_cell(0, 6, f"\u2022 {question}")

    return pdf.output()


__all__ = [
    "render_pdf",
]
