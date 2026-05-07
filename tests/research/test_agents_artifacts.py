from __future__ import annotations

import pytest

from compendiumscribe.research.agents_workflow import (
    CompendiumPayload,
    SectionResearchBrief,
    SourceLedger,
    SourceLedgerEntry,
    build_source_ledger,
    mark_cited_sources,
    normalize_url,
    prepare_compendium_payload,
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


def test_normalize_url_promotes_scheme_less_hosts_to_https() -> None:
    assert normalize_url("example.com/source") == "https://example.com/source"
    assert normalize_url("localhost/report/") == "https://localhost/report"
    assert normalize_url("http://Example.com/report/") == (
        "http://example.com/report"
    )


def test_source_ledger_matches_scheme_less_source_urls_to_cited_urls() -> None:
    brief = SectionResearchBrief(
        section_id="s1",
        title="One",
        summary="Summary",
        findings=[
            {
                "title": "Finding",
                "evidence": "Evidence",
                "source_urls": ["https://example.com/source"],
            }
        ],
        sources=[
            {
                "title": "Source",
                "url": "example.com/source",
                "status": "consulted",
            }
        ],
    )
    ledger = build_source_ledger([brief])

    mark_cited_sources(
        ledger,
        [
            source_url
            for finding in brief.findings
            for source_url in finding.source_urls
        ],
    )

    assert ledger.entries[0].url == "https://example.com/source"
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


def test_prepare_compendium_payload_hydrates_citations_from_ledger() -> None:
    ledger = SourceLedger(
        entries=[
            SourceLedgerEntry(
                id="C01",
                title="Authoritative first source",
                url="https://example.com/first",
                publisher="Example",
                status="cited",
            ),
            SourceLedgerEntry(
                id="C02",
                title="Authoritative second source",
                url="https://example.com/second",
                publisher="Example",
                status="cited",
            ),
        ]
    )
    payload = CompendiumPayload(
        topic_overview="Overview",
        sections=[
            {
                "id": "s1",
                "title": "Section",
                "summary": "Summary",
                "insights": [
                    {
                        "title": "Finding one",
                        "evidence": "Evidence",
                        "citations": ["C02"],
                    },
                    {
                        "title": "Finding two",
                        "evidence": "Evidence",
                        "citations": ["C01", "C02"],
                    },
                ],
            }
        ],
        citations=[
            {
                "id": "C01",
                "title": "Model-supplied title",
                "url": "https://wrong.example.com",
            }
        ],
    )

    prepared = prepare_compendium_payload(payload, ledger)

    assert [citation.id for citation in prepared.citations] == ["C02", "C01"]
    assert prepared.citations[0].title == "Authoritative second source"
    assert prepared.citations[0].url == "https://example.com/second"
    assert prepared.citations[1].title == "Authoritative first source"
    assert prepared.citations[1].url == "https://example.com/first"
