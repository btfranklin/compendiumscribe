"""Parse Compendium XML back into Compendium objects."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .compendium import Compendium
from .entities import Citation, Insight, Section


def parse_xml_file(path: Path | str) -> Compendium:
    """Parse a Compendium from an XML file."""
    tree = ET.parse(path)
    return _parse_root(tree.getroot())


def parse_xml_string(content: str) -> Compendium:
    """Parse a Compendium from an XML string."""
    root = ET.fromstring(content)
    return _parse_root(root)


def _get_text(elem: ET.Element | None, default: str = "") -> str:
    """Get text content of an element, handling None."""
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def _get_text_or_none(elem: ET.Element | None) -> str | None:
    """Get text content of an element, returning None if empty/missing."""
    if elem is None or not elem.text:
        return None
    text = elem.text.strip()
    return text if text else None


def _parse_root(root: ET.Element) -> Compendium:
    """Parse the root <compendium> element."""
    if root.tag != "compendium":
        raise ValueError(f"Expected <compendium> root tag, got <{root.tag}>")

    topic = root.attrib.get("topic", "Untitled")
    generated_at_str = root.attrib.get("generated_at")
    generated_at = None
    if generated_at_str:
        try:
            generated_at = datetime.fromisoformat(generated_at_str)
        except ValueError:
            # Fallback to default (now) in Compendium constructor if needed.
            pass

    overview = _get_text(root.find("overview"))

    methodology: list[str] = []
    meth_elem = root.find("methodology")
    if meth_elem is not None:
        for step in meth_elem.findall("step"):
            methodology.append(_get_text(step))

    sections: list[Section] = []
    sections_elem = root.find("sections")
    if sections_elem is not None:
        for sec_elem in sections_elem.findall("section"):
            sections.append(_parse_section(sec_elem))

    citations: list[Citation] = []
    citations_elem = root.find("citations")
    if citations_elem is not None:
        for cit_elem in citations_elem.findall("citation"):
            citations.append(_parse_citation(cit_elem))

    open_questions: list[str] = []
    questions_elem = root.find("open_questions")
    if questions_elem is not None:
        for q_elem in questions_elem.findall("question"):
            open_questions.append(_get_text(q_elem))

    compendium = Compendium(
        topic=topic,
        overview=overview,
        methodology=methodology,
        sections=sections,
        citations=citations,
        open_questions=open_questions,
    )

    if generated_at:
        compendium.generated_at = generated_at

    return compendium


def _parse_section(elem: ET.Element) -> Section:
    """Parse a <section> element."""
    identifier = elem.attrib.get("id", "")
    title = _get_text(elem.find("title"))
    summary = _get_text(elem.find("summary"))

    key_terms: list[str] = []
    terms_elem = elem.find("key_terms")
    if terms_elem is not None:
        for term in terms_elem.findall("term"):
            key_terms.append(_get_text(term))

    guiding_questions: list[str] = []
    gq_elem = elem.find("guiding_questions")
    if gq_elem is not None:
        for q in gq_elem.findall("question"):
            guiding_questions.append(_get_text(q))

    insights: list[Insight] = []
    insights_elem = elem.find("insights")
    if insights_elem is not None:
        for ins_elem in insights_elem.findall("insight"):
            insights.append(_parse_insight(ins_elem))

    return Section(
        identifier=identifier,
        title=title,
        summary=summary,
        key_terms=key_terms,
        guiding_questions=guiding_questions,
        insights=insights,
    )


def _parse_insight(elem: ET.Element) -> Insight:
    """Parse an <insight> element."""
    title = _get_text(elem.find("title"))
    evidence = _get_text(elem.find("evidence"))
    implications = _get_text_or_none(elem.find("implications"))

    citation_refs: list[str] = []
    refs_elem = elem.find("citations")
    if refs_elem is not None:
        for ref in refs_elem.findall("ref"):
            citation_refs.append(_get_text(ref))

    return Insight(
        title=title,
        evidence=evidence,
        implications=implications,
        citation_refs=citation_refs,
    )


def _parse_citation(elem: ET.Element) -> Citation:
    """Parse a <citation> element."""
    identifier = elem.attrib.get("id", "")
    title = _get_text(elem.find("title"))
    url = _get_text(elem.find("url"))
    publisher = _get_text_or_none(elem.find("publisher"))
    published_at = _get_text_or_none(elem.find("published_at"))
    summary = _get_text_or_none(elem.find("summary"))

    return Citation(
        identifier=identifier,
        title=title,
        url=url,
        publisher=publisher,
        published_at=published_at,
        summary=summary,
    )
