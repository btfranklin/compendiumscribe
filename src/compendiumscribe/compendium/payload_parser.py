from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .entities import Citation, Insight, Section

if TYPE_CHECKING:  # pragma: no cover - hints only
    from .compendium import Compendium


def build_from_payload(
    cls: type["Compendium"],
    topic: str,
    payload: dict[str, Any],
    generated_at: datetime | None = None,
) -> "Compendium":
    """Create a compendium instance from a raw payload."""

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

    return cls(
        topic=topic,
        overview=overview,
        methodology=methodology,
        sections=sections,
        citations=citations,
        open_questions=open_questions,
        generated_at=generated_at or datetime.now(timezone.utc),
    )


__all__ = ["build_from_payload"]
