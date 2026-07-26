from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from compendiumscribe.compendium import Citation, Compendium, Section
from compendiumscribe.library import (
    import_compendium,
    list_library_entries,
    publish_compendium,
    validate_library,
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
        generated_at=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
    )


def test_publish_compendium_creates_strict_okf_library(
    tmp_path: Path,
) -> None:
    library_path = tmp_path / "library"

    entry = publish_compendium(sample_compendium(), library_path)

    assert entry.id == "evaluating-ai-agents"
    assert entry.path == "compendiums/evaluating-ai-agents"
    assert entry.tags[:2] == ("evaluating", "operational")
    assert validate_library(library_path) == ()
    assert sorted(
        path.relative_to(library_path).as_posix()
        for path in library_path.rglob("*")
        if path.is_file()
    ) == [
        "compendiums/evaluating-ai-agents/compendium.md",
        "compendiums/evaluating-ai-agents/index.md",
        "compendiums/evaluating-ai-agents/sections/index.md",
        "compendiums/evaluating-ai-agents/sections/sec-1.md",
        "compendiums/evaluating-ai-agents/sections/sec-2.md",
        "compendiums/evaluating-ai-agents/sources/c1.md",
        "compendiums/evaluating-ai-agents/sources/index.md",
        "compendiums/index.md",
        "index.md",
    ]
    assert not list(library_path.rglob("*.xml"))
    assert not list(library_path.rglob("*.json"))
    assert not list(library_path.rglob("log.md"))


def test_publish_replaces_same_entry_and_removes_stale_files(
    tmp_path: Path,
) -> None:
    library_path = tmp_path / "library"
    first = publish_compendium(sample_compendium(), library_path)
    stale_path = library_path / first.path / "manual.md"
    stale_path.write_text("---\ntype: Note\n---\n\nManual.\n", encoding="utf-8")
    updated = sample_compendium(overview="Updated overview.")
    updated.sections = updated.sections[:1]

    second = publish_compendium(updated, library_path)

    assert first.id == second.id
    assert second.description == "Updated overview."
    assert not stale_path.exists()
    assert not (
        library_path
        / second.path
        / "sections"
        / "sec-2.md"
    ).exists()
    assert validate_library(library_path) == ()


def test_publish_appends_suffix_for_slug_collision(tmp_path: Path) -> None:
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
    assert [entry.id for entry in list_library_entries(library_path)] == [
        "agent-safety",
        "agent-safety-2",
    ]
    assert validate_library(library_path) == ()


def test_import_xml_converts_to_okf(tmp_path: Path) -> None:
    source = sample_compendium(topic="Imported Research")
    xml_path = tmp_path / "source.xml"
    xml_path.write_text(source.to_xml_string(), encoding="utf-8")
    library_path = tmp_path / "library"

    entry = import_compendium(
        library_path=library_path,
        source_path=xml_path,
    )

    assert entry.id == "imported-research"
    assert (library_path / entry.path / "compendium.md").exists()
    assert not list((library_path / entry.path).rglob("*.xml"))
    assert validate_library(library_path) == ()


def test_import_okf_preserves_unknown_frontmatter(tmp_path: Path) -> None:
    source_path = tmp_path / "source.okf"
    from compendiumscribe.compendium import write_okf_bundle

    source = sample_compendium(topic="Imported OKF")
    files = source.to_okf_bundle()
    files["compendium.md"] = files["compendium.md"].replace(
        "profile: compendiumscribe\n",
        "custom_field: retained\nprofile: compendiumscribe\n",
    )
    write_okf_bundle(source_path, files)

    library_path = tmp_path / "library"
    entry = import_compendium(
        library_path=library_path,
        source_path=source_path,
    )

    content = (
        library_path / entry.path / "compendium.md"
    ).read_text(encoding="utf-8")
    assert "custom_field: retained" in content
    assert validate_library(library_path) == ()


def test_validation_reports_stale_inventory_and_non_markdown(
    tmp_path: Path,
) -> None:
    library_path = tmp_path / "library"
    publish_compendium(sample_compendium(), library_path)
    (library_path / "compendiums" / "index.md").write_text(
        "# Compendiums\n",
        encoding="utf-8",
    )
    (library_path / "unexpected.xml").write_text("<x/>", encoding="utf-8")

    issues = validate_library(library_path)

    assert {issue.code for issue in issues} >= {
        "inventory_index_stale",
        "unexpected_library_file",
    }
