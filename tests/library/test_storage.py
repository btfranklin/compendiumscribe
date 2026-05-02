from __future__ import annotations

import json
from pathlib import Path

from compendiumscribe.compendium import Citation, Compendium, Section
from compendiumscribe.library import (
    build_card,
    import_compendium_xml,
    load_catalog,
    publish_compendium,
)


def sample_compendium(
    *,
    topic: str = "Evaluating AI Agents",
    overview: str = "A practical overview of agent evaluation in production.",
) -> Compendium:
    return Compendium(
        topic=topic,
        overview=overview,
        sections=[
            Section(
                identifier="sec-1",
                title="Operational Metrics",
                summary="Track task success, latency, escalation, and drift.",
                key_terms=["task success", "latency", "drift"],
            ),
            Section(
                identifier="sec-2",
                title="Human Review",
                summary="Use sampled review and incident analysis.",
                key_terms=["review", "incident analysis"],
            ),
        ],
        citations=[
            Citation(
                identifier="C1",
                title="Agent Evals",
                url="https://example.com/evals",
            )
        ],
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_publish_compendium_creates_catalog_card_xml_and_markdown(
    tmp_path: Path,
) -> None:
    library_path = tmp_path / "library"

    entry = publish_compendium(sample_compendium(), library_path)

    assert entry.id == "evaluating-ai-agents"
    assert entry.path == "compendiums/evaluating-ai-agents/compendium.xml"
    assert entry.markdown_path == (
        "compendiums/evaluating-ai-agents/compendium.md"
    )
    assert entry.card_path == "compendiums/evaluating-ai-agents/card.json"

    catalog = read_json(library_path / "catalog.json")
    assert catalog["schema_version"] == 1
    assert len(catalog["entries"]) == 1
    assert catalog["entries"][0]["id"] == entry.id
    assert catalog["entries"][0]["path"] == entry.path

    card = read_json(library_path / entry.card_path)
    assert card["title"] == "Evaluating AI Agents"
    assert card["section_count"] == 2
    assert card["citation_count"] == 1
    assert card["source_count"] == 1
    assert card["path"] == entry.path
    assert card["markdown_path"] == entry.markdown_path
    assert card["sections"][0]["title"] == "Operational Metrics"

    xml = library_path / entry.path
    markdown = library_path / entry.markdown_path
    assert xml.exists()
    assert 'topic="Evaluating AI Agents"' in xml.read_text(
        encoding="utf-8"
    )
    assert "# Evaluating AI Agents" in markdown.read_text(encoding="utf-8")


def test_publish_compendium_upserts_same_slug_and_preserves_created_at(
    tmp_path: Path,
) -> None:
    library_path = tmp_path / "library"
    first = publish_compendium(sample_compendium(), library_path)
    second = publish_compendium(
        sample_compendium(overview="Updated overview."),
        library_path,
    )

    catalog = load_catalog(library_path)
    assert first.id == second.id
    assert len(catalog.entries) == 1
    assert catalog.entries[0].summary == "Updated overview."
    assert catalog.entries[0].created_at == first.created_at
    assert catalog.entries[0].updated_at >= first.updated_at


def test_publish_compendium_appends_suffix_for_slug_collision(
    tmp_path: Path,
) -> None:
    library_path = tmp_path / "library"
    first = publish_compendium(
        sample_compendium(topic="Agent Safety"),
        library_path,
    )
    second = publish_compendium(
        sample_compendium(topic="Agent Safety!"),
        library_path,
    )

    assert first.id == "agent-safety"
    assert second.id == "agent-safety-2"
    catalog = load_catalog(library_path)
    assert {entry.id for entry in catalog.entries} == {
        "agent-safety",
        "agent-safety-2",
    }


def test_build_card_truncates_summary_and_derives_keywords() -> None:
    compendium = sample_compendium(overview=" ".join(["summary"] * 120))

    card = build_card(compendium, entry_id="evaluating-ai-agents")

    assert len(card.summary) <= 500
    assert card.summary.endswith("...")
    assert "evaluating" in card.keywords
    assert "operational" in card.keywords
    assert "task success" in card.keywords


def test_import_compendium_xml_normalizes_outputs(
    tmp_path: Path,
) -> None:
    source = sample_compendium(topic="Imported Research")
    xml_path = tmp_path / "source.xml"
    xml_path.write_text(source.to_xml_string(), encoding="utf-8")
    library_path = tmp_path / "library"

    entry = import_compendium_xml(
        library_path=library_path,
        compendium_xml=xml_path,
    )

    assert entry.id == "imported-research"
    assert (library_path / entry.path).exists()
    assert (library_path / entry.markdown_path).exists()
    assert (library_path / entry.card_path).exists()
    assert load_catalog(library_path).entries[0].title == "Imported Research"
