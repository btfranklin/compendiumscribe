"""Tests for XML parsing and round-tripping."""

from __future__ import annotations

from datetime import datetime, timezone

from compendiumscribe.compendium import (
    Citation,
    Compendium,
    Insight,
    Section,
)
from compendiumscribe.compendium.xml_parser import parse_xml_string


def _create_full_compendium() -> Compendium:
    """Create a populated Compendium object for testing."""
    return Compendium(
        topic="XML Round Trip",
        overview="Testing deserialization fidelity.",
        methodology=["Parse XML", "Compare objects"],
        sections=[
            Section(
                identifier="S1",
                title="Parsing Logic",
                summary="Details on how parsing works.",
                key_terms=["ETree", "Serialization"],
                guiding_questions=["Is it lossless?"],
                insights=[
                    Insight(
                        title="Fidelity verified",
                        evidence="Unit tests pass.",
                        implications="We can rely on XML storage.",
                        citation_refs=["C1"],
                    )
                ],
            )
        ],
        citations=[
            Citation(
                identifier="C1",
                title="Python XML Docs",
                url="https://docs.python.org/3/library/xml.etree.elementtree.html",
                publisher="Python Software Foundation",
                published_at="2024-10-01",
                summary="Official documentation.",
            )
        ],
        open_questions=["What about future schema changes?"],
        generated_at=datetime(2024, 12, 16, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_round_trip_serialization():
    """Verify that an object converted to XML and back matches the original."""
    original = _create_full_compendium()
    
    # 1. Serialize to XML string
    xml_output = original.to_xml_string()
    
    # 2. Parse back to object
    reconstructed = parse_xml_string(xml_output)
    
    # 3. Assert equality
    assert reconstructed.topic == original.topic
    assert reconstructed.overview == original.overview
    assert reconstructed.methodology == original.methodology
    assert reconstructed.open_questions == original.open_questions
    assert reconstructed.generated_at == original.generated_at
    
    # Sections match
    assert len(reconstructed.sections) == len(original.sections)
    s1_orig = original.sections[0]
    s1_new = reconstructed.sections[0]
    assert s1_new.identifier == s1_orig.identifier
    assert s1_new.title == s1_orig.title
    assert s1_new.summary == s1_orig.summary
    assert s1_new.key_terms == s1_orig.key_terms
    assert s1_new.guiding_questions == s1_orig.guiding_questions
    
    # Insights match
    assert len(s1_new.insights) == len(s1_orig.insights)
    i1_orig = s1_orig.insights[0]
    i1_new = s1_new.insights[0]
    assert i1_new.title == i1_orig.title
    assert i1_new.evidence == i1_orig.evidence
    assert i1_new.implications == i1_orig.implications
    assert i1_new.citation_refs == i1_orig.citation_refs
    
    # Citations match
    assert len(reconstructed.citations) == len(original.citations)
    c1_orig = original.citations[0]
    c1_new = reconstructed.citations[0]
    assert c1_new.identifier == c1_orig.identifier
    assert c1_new.title == c1_orig.title
    assert c1_new.url == c1_orig.url
    assert c1_new.publisher == c1_orig.publisher
    assert c1_new.published_at == c1_orig.published_at
    assert c1_new.summary == c1_orig.summary


def test_minimal_object_round_trip():
    """Verify round-trip works for objects with optional fields missing."""
    minimal = Compendium(
        topic="Minimal",
        overview="Just basics.",
    )
    # Ensure generated_at is fixed for comparison, or ignore it
    minimal.generated_at = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    xml_output = minimal.to_xml_string()
    reconstructed = parse_xml_string(xml_output)
    
    assert reconstructed.topic == "Minimal"
    assert reconstructed.overview == "Just basics."
    assert reconstructed.methodology == []
    assert reconstructed.sections == []
    assert reconstructed.citations == []
    assert reconstructed.open_questions == []


def test_missing_root_tag_raises_error():
    """Verify invalid XML structure raises ValueError."""
    invalid_xml = "<invalid>Content</invalid>"
    try:
        parse_xml_string(invalid_xml)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Expected <compendium> root tag" in str(e)


def test_markdown_links_are_preserved():
    """Verify that Markdown links are preserved in XML serialization."""
    compendium = Compendium(
        topic="Link Test",
        overview="Check [Link](https://example.com) preservation.",
    )
    
    xml_output = compendium.to_xml_string()
    
    # Verify XML content has the markdown link, NOT the flattened version
    assert "[Link](https://example.com)" in xml_output
    assert "Link (https://example.com)" not in xml_output
    
    # Verify round-trip
    reconstructed = parse_xml_string(xml_output)
    assert reconstructed.overview == "Check [Link](https://example.com) preservation."
