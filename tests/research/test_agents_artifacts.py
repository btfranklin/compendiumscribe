from __future__ import annotations

import pytest

from compendiumscribe.research.agents_workflow import (
    CompendiumPayload,
    SectionResearchBrief,
    build_source_ledger,
    validate_compendium_citations,
)


def test_payload_maps_to_compendium() -> None:
    from compendiumscribe.compendium import Compendium

    payload = CompendiumPayload(
        topic_overview="Overview",
        methodology=["Checked sources."],
        sections=[
            {
                "id": "s1",
                "title": "Section",
                "summary": "Summary",
                "insights": [
                    {
                        "title": "Finding",
                        "evidence": "Evidence",
                        "citations": ["C01"],
                    }
                ],
            }
        ],
        citations=[
            {
                "id": "C01",
                "title": "Citation",
                "url": "https://example.com/citation",
            }
        ],
    )

    compendium = Compendium.from_payload("Topic", payload.to_payload())

    assert compendium.overview == "Overview"
    assert compendium.sections[0].insights[0].citation_refs == ["C01"]


def test_source_ledger_deduplicates_urls_and_keeps_section_usage() -> None:
    brief_one = SectionResearchBrief(
        section_id="s1",
        title="One",
        summary="Summary",
        sources=[
            {
                "title": "Shared Source",
                "url": "https://Example.com/report?utm=x",
                "status": "cited",
            }
        ],
    )
    brief_two = SectionResearchBrief(
        section_id="s2",
        title="Two",
        summary="Summary",
        sources=[
            {
                "title": "Shared Source",
                "url": "https://example.com/report#section",
                "status": "consulted",
            }
        ],
    )

    ledger = build_source_ledger([brief_one, brief_two])

    assert len(ledger.entries) == 1
    assert ledger.entries[0].id == "C01"
    assert ledger.entries[0].section_ids == ["s1", "s2"]
    assert ledger.entries[0].status == "cited"


def test_rejected_and_consulted_only_sources_cannot_be_final_citations() -> None:
    brief = SectionResearchBrief(
        section_id="s1",
        title="One",
        summary="Summary",
        sources=[
            {
                "title": "Consulted",
                "url": "https://example.com/consulted",
                "status": "consulted",
            },
            {
                "title": "Rejected",
                "url": "https://example.com/rejected",
                "status": "rejected",
            },
        ],
    )
    ledger = build_source_ledger([brief])
    payload = CompendiumPayload(
        topic_overview="Overview",
        sections=[
            {
                "id": "s1",
                "title": "Section",
                "summary": "Summary",
                "insights": [
                    {
                        "title": "Finding",
                        "evidence": "Evidence",
                        "citations": ["C01"],
                    }
                ],
            }
        ],
        citations=[
            {
                "id": "C01",
                "title": "Consulted",
                "url": "https://example.com/consulted",
            }
        ],
    )

    assert len(ledger.entries) == 1
    with pytest.raises(ValueError, match="unknown citation IDs"):
        validate_compendium_citations(payload, ledger)
