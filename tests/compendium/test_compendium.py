from __future__ import annotations

import xml.etree.ElementTree as ET

from compendiumscribe.compendium import (
    Citation,
    Compendium,
    Insight,
    Section,
    etree_to_string,
)


def test_compendium_to_xml_contains_expected_structure():
    compendium = Compendium(
        topic="Quantum Computing",
        overview="High-level synthesis",
        methodology=["Map core concepts", "Cross-validate findings"],
        sections=[
            Section(
                identifier="S1",
                title="Foundations",
                summary="Qubits and quantum gates",
                key_terms=["qubit", "superposition"],
                guiding_questions=[
                    "What distinguishes qubits from classical bits?"
                ],
                insights=[
                    Insight(
                        title="Coherence is fragile",
                        evidence=(
                            "Most systems retain coherence for microseconds"
                            " before error correction overwhelms throughput."
                        ),
                        implications=(
                            "Large-scale machines require aggressive error"
                            " mitigation."
                        ),
                        citation_refs=["C1"],
                    )
                ],
            )
        ],
        citations=[
            Citation(
                identifier="C1",
                title="A Survey on Quantum Error Correction",
                url="https://example.com/qec",
                publisher="ACM",
                published_at="2023-04-01",
                summary=(
                    "Overview of leading quantum error correction"
                    " strategies."
                ),
            )
        ],
        open_questions=["When will logical qubits exceed 100 by default?"],
    )

    xml_string = compendium.to_xml_string()
    root = ET.fromstring(xml_string)

    assert root.tag == "compendium"
    assert root.attrib["topic"] == "Quantum Computing"
    assert root.findtext("overview") == "High-level synthesis"
    assert root.find("sections/section/title").text == "Foundations"
    assert (
        root.find("citations/citation/title").text
        == "A Survey on Quantum Error Correction"
    )
    assert root.find("research_trace") is None

    lines = xml_string.splitlines()
    assert lines[0].startswith("<compendium")
    assert any(line.startswith("  <sections>") for line in lines)
    assert lines[-1] == "</compendium>"


def test_compendium_additional_exports():
    compendium = Compendium(
        topic="Synthetic Biology",
        overview="Interdisciplinary insights",
        methodology=["Review literature", "Synthesize expert views"],
        sections=[],
        citations=[],
        open_questions=[],
    )

    markdown = compendium.to_markdown()
    assert markdown.startswith("# Synthetic Biology")
    assert "## Overview" in markdown
    assert "Research Trace" not in markdown

    html_doc = compendium.to_html()
    assert html_doc.lstrip().startswith("<!DOCTYPE html>")
    assert "Synthetic Biology" in html_doc
    assert "Research Trace" not in html_doc

    pdf_bytes = compendium.to_pdf_bytes()
    assert pdf_bytes.startswith(b"%PDF-1.4\n")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")


def test_inline_links_render_per_format():
    compendium = Compendium(
        topic="Inline Link Rendering",
        overview="See [Example](https://example.com) reference.",
        methodology=["Review [Docs](https://docs.example.com)"],
        sections=[
            Section(
                identifier="S1",
                title="Context",
                summary="Use [Guide](https://guide.example.com) often.",
                key_terms=["[Term](https://term.example.com)"],
                guiding_questions=[
                    "What is [link](https://q.example.com)?"
                ],
                insights=[
                    Insight(
                        title="Linked insight",
                        evidence=(
                            "Check [evidence](https://evidence.example.com)."
                        ),
                        implications=(
                            "Consider [impact](https://impact.example.com)."
                        ),
                    )
                ],
            )
        ],
        citations=[
            Citation(
                identifier="C1",
                title="[Citation](https://citation.example.com)",
                url="https://citation.example.com",
                summary="Summarize [source](https://source.example.com).",
            )
        ],
        open_questions=["Next [steps](https://steps.example.com)?"],
    )

    markdown = compendium.to_markdown()
    assert "[Example](https://example.com)" in markdown

    html_doc = compendium.to_html()
    anchor = (
        "<a href=\"https://example.com\" rel=\"noopener noreferrer\">"
        "Example</a>"
    )
    assert anchor in html_doc
    assert "[Example](https://example.com)" not in html_doc

    xml_root = ET.fromstring(compendium.to_xml_string())
    assert (
        xml_root.findtext("overview")
        == "See [Example](https://example.com) reference."
    )

    plain_text = "\n".join(compendium._plain_text_lines())
    assert "Example (https://example.com)" in plain_text
    assert "[Example](https://example.com)" not in plain_text


def test_compendium_from_payload_normalizes_fields():
    payload = {
        "topic_overview": "A concise overview",
        "methodology": [
            "Collect expert commentary",
            "Highlight quantitative indicators",
        ],
        "sections": [
            {
                "id": "S1",
                "title": "Key Dynamics",
                "summary": "Market movements and investment levels",
                "key_terms": ["capex"],
                "guiding_questions": ["Which regions are scaling fastest?"],
                "insights": [
                    {
                        "title": "Private investment surged",
                        "evidence": (
                            "Funding grew 45% year over year according to"
                            " PitchBook."
                        ),
                        "implications": (
                            "Competition for talent is increasing."
                        ),
                        "citations": ["C1"],
                    }
                ],
            }
        ],
        "citations": [
            {
                "id": "C1",
                "title": "PitchBook Emerging Tech Report",
                "url": "https://example.com/pitchbook",
                "publisher": "PitchBook",
                "published_at": "2024-01-15",
                "summary": "Investment trends across quantum startups.",
            }
        ],
        "open_questions": ["How will regulation shape deployment?"],
    }

    compendium = Compendium.from_payload("Quantum Capital", payload)

    assert compendium.topic == "Quantum Capital"
    assert compendium.methodology[0] == "Collect expert commentary"
    assert compendium.sections[0].insights[0].citation_refs == ["C1"]
    assert compendium.citations[0].publisher == "PitchBook"
    assert compendium.open_questions == [
        "How will regulation shape deployment?"
    ]
    assert not hasattr(compendium, "trace")


def test_etree_to_string_preserves_cdata_when_requested():
    root = ET.Element("note")
    content = ET.SubElement(root, "content")
    content.text = "Important <data>"

    xml = etree_to_string(root, cdata_tags={"content"})

    assert "<![CDATA[Important <data>]]>" in xml
