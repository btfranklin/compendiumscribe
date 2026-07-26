from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from compendiumscribe.compendium import (
    Citation,
    Compendium,
    Insight,
    OKFError,
    Section,
    validate_okf_bundle,
    write_okf_bundle,
)
from compendiumscribe.compendium.okf import validate_okf_mapping


def full_compendium() -> Compendium:
    return Compendium(
        topic="Synthetic [Biology]",
        overview="Overview with **Markdown**.\n# Embedded heading",
        methodology=["First step", "Line one\nLine two"],
        sections=[
            Section(
                identifier="S01",
                title="Methods",
                summary="A summary with [a link](https://example.com).",
                key_terms=["biology", "methods"],
                guiding_questions=["What works?", "Why?"],
                insights=[
                    Insight(
                        title="Primary insight",
                        evidence="Evidence.\n# Not a profile heading",
                        implications="Implications.",
                        citation_refs=["C01", "C02"],
                    ),
                    Insight(
                        title="Secondary insight",
                        evidence="More evidence.",
                        citation_refs=[],
                    ),
                ],
            )
        ],
        citations=[
            Citation(
                identifier="C01",
                title="Source [One]",
                url="https://example.com/one",
                publisher="Publisher",
                published_at="2026-07-01",
                summary="Source summary.",
            ),
            Citation(
                identifier="C02",
                title="Source Two",
                url="https://example.com/two?a=1&b=2",
            ),
        ],
        open_questions=["What next?", "Question\ncontinued"],
        generated_at=datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc),
    )


def test_okf_bundle_has_exact_layout_and_profile() -> None:
    files = full_compendium().to_okf_bundle()

    assert list(files) == [
        "compendium.md",
        "index.md",
        "sections/index.md",
        "sections/s01.md",
        "sources/c01.md",
        "sources/c02.md",
        "sources/index.md",
    ]
    assert "profile: compendiumscribe" in files["compendium.md"]
    assert "profile_version: '1'" in files["compendium.md"]
    assert "tags:" in files["compendium.md"]
    assert "../sources/c01.md" in files["sections/s01.md"]
    assert "../sources/c02.md" in files["sections/s01.md"]
    assert not any(path.endswith("log.md") for path in files)
    assert validate_okf_mapping(files) == ()


def test_okf_round_trip_preserves_core_model(tmp_path: Path) -> None:
    original = full_compendium()
    bundle_path = tmp_path / "report.okf"

    write_okf_bundle(bundle_path, original.to_okf_bundle())
    restored = Compendium.from_okf_bundle(bundle_path)

    assert restored == original
    assert validate_okf_bundle(bundle_path) == ()


def test_empty_bundle_still_has_section_and_source_indexes(
    tmp_path: Path,
) -> None:
    compendium = Compendium(topic="Empty", overview="")
    bundle_path = tmp_path / "empty.okf"

    write_okf_bundle(bundle_path, compendium.to_okf_bundle())

    assert (bundle_path / "sections/index.md").read_text(
        encoding="utf-8"
    ) == "# Sections\n\nNo sections.\n"
    assert (bundle_path / "sources/index.md").read_text(
        encoding="utf-8"
    ) == "# Sources\n\nNo sources.\n"
    assert Compendium.from_okf_bundle(bundle_path) == compendium


def test_duplicate_normalized_section_ids_are_rejected() -> None:
    compendium = full_compendium()
    compendium.sections.append(
        Section(identifier="s01!", title="Collision", summary="")
    )

    with pytest.raises(OKFError, match="collide"):
        compendium.to_okf_bundle()


def test_unknown_citation_reference_is_rejected() -> None:
    compendium = full_compendium()
    compendium.sections[0].insights[0].citation_refs.append("missing")

    with pytest.raises(OKFError, match="unknown citation"):
        compendium.to_okf_bundle()


def test_unknown_frontmatter_is_accepted(tmp_path: Path) -> None:
    files = full_compendium().to_okf_bundle()
    files["compendium.md"] = files["compendium.md"].replace(
        "profile: compendiumscribe\n",
        "arbitrary_field: allowed\nprofile: compendiumscribe\n",
    )
    bundle_path = tmp_path / "report.okf"

    write_okf_bundle(bundle_path, files)

    assert validate_okf_bundle(bundle_path) == ()


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda files: files.__setitem__(
                "compendium.md",
                files["compendium.md"].replace("type: Compendium\n", ""),
            ),
            "required_field_missing",
        ),
        (
            lambda files: files.__setitem__(
                "compendium.md",
                files["compendium.md"].replace(
                    "profile_version: '1'",
                    "profile_version: '2'",
                ),
            ),
            "profile_field_invalid",
        ),
        (
            lambda files: files.__setitem__(
                "log.md",
                "# Log\n",
            ),
            "log_forbidden",
        ),
        (
            lambda files: files.__setitem__(
                "index.md",
                files["index.md"].replace(
                    "./sections/",
                    "../sections/",
                ),
            ),
            "path_traversal",
        ),
        (
            lambda files: files.__setitem__(
                "compendium.md",
                files["compendium.md"].replace(
                    "tags:",
                    "broken: [\ntags:",
                    1,
                ),
            ),
            "invalid_frontmatter",
        ),
        (
            lambda files: files.__setitem__(
                "sections/index.md",
                files["sections/index.md"].replace(
                    "./s01.md",
                    "./missing.md",
                ),
            ),
            "broken_index_link",
        ),
        (
            lambda files: files.__setitem__(
                "compendium.md",
                files["compendium.md"].replace(
                    "tags:\n- synthetic\n- biology\n- methods\n",
                    "tags: invalid\n",
                    1,
                ),
            ),
            "invalid_tags",
        ),
        (
            lambda files: files.__setitem__(
                "compendium.md",
                files["compendium.md"].replace(
                    "timestamp: '2026-07-22T15:00:00+00:00'",
                    "timestamp: not-a-time",
                ),
            ),
            "invalid_timestamp",
        ),
    ],
)
def test_validation_reports_stable_codes(mutate, expected_code) -> None:
    files = full_compendium().to_okf_bundle()
    mutate(files)

    assert expected_code in {
        issue.code for issue in validate_okf_mapping(files)
    }


def test_validation_rejects_symlink_and_non_markdown(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "report.okf"
    write_okf_bundle(bundle_path, full_compendium().to_okf_bundle())
    (bundle_path / "extra.xml").write_text("<x/>", encoding="utf-8")
    (bundle_path / "linked.md").symlink_to(bundle_path / "compendium.md")

    codes = {issue.code for issue in validate_okf_bundle(bundle_path)}

    assert {"non_markdown_file", "symlink_forbidden"} <= codes
