import json
import os
import pytest
from click.testing import CliRunner
from pathlib import Path
from unittest import mock
from compendiumscribe.cli import cli
from compendiumscribe.compendium import Citation, Compendium, Section
from compendiumscribe.research.errors import DeepResearchError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_build_compendium():
    with mock.patch("compendiumscribe.cli.build_compendium") as mock_build:
        compendium = mock.Mock(spec=Compendium)
        compendium.topic = "Test Title"
        compendium.overview = "Overview text."
        compendium.methodology = []
        compendium.sections = [
            Section(
                identifier="sec-1",
                title="Test Section",
                summary="Section summary.",
                key_terms=["testing"],
            )
        ]
        compendium.citations = [
            Citation(
                identifier="C1",
                title="Example Source",
                url="https://example.com/source",
            )
        ]
        compendium.open_questions = []
        compendium.to_markdown.return_value = "# Markdown Content"
        compendium.to_xml_string.return_value = (
            '<compendium topic="Test Title"><overview>Overview text.'
            "</overview></compendium>"
        )
        compendium.to_html_site.return_value = {
            "index.html": "<html>Index</html>",
        }
        compendium.to_pdf_bytes.return_value = b"PDF Content"

        def build_side_effect(*_args, **kwargs):
            state_path = kwargs.get("state_path")
            if state_path is not None:
                state_path.write_text("{}", encoding="utf-8")
            return compendium

        mock_build.side_effect = build_side_effect
        yield mock_build


@pytest.fixture
def mock_create_client():
    with mock.patch(
        "compendiumscribe.cli.create_openai_client"
    ) as mock_client:
        yield mock_client


def test_cli_create_default_format_is_markdown(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["create", "Test Topic"],
        )
        assert result.exit_code == 0, result.output

        # Should generate a markdown file by default
        files = list(Path(".").glob("*.md"))
        assert len(files) == 1
        assert "test-topic" in files[0].name
        assert files[0].read_text() == "# Markdown Content"
        assert len(list(Path(".").glob("*.research.json"))) == 1
        assert len(list(Path(".").glob("*.costs.json"))) == 1
        assert not Path("catalog.json").exists()
        assert not Path("compendiums").exists()
        assert (
            mock_build_compendium.call_args.kwargs["client"]
            is mock_create_client.return_value
        )


def test_cli_create_reports_unknown_profile_as_configuration_error(
    runner,
    mock_create_client,
) -> None:
    with mock.patch.dict(
        os.environ,
        {"CONTRACT4AGENTS_PROFILE": "missing"},
    ):
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["create", "Test Topic"])

            assert result.exit_code == 1
            assert "Configuration error:" in result.output
            assert "Unknown Contract4Agents OpenAI profile: missing" in result.output
            assert "Unexpected error:" not in result.output
            assert not list(Path(".").glob("*.costs.json"))


def test_cli_create_format_xml(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["create", "Test Topic", "--format", "xml"],
        )
        assert result.exit_code == 0

        files = list(Path(".").glob("*.xml"))
        assert len(files) == 1
        assert files[0].read_text() == (
            '<compendium topic="Test Title"><overview>Overview text.'
            "</overview></compendium>"
        )


def test_cli_create_multiple_formats(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "create",
                "Test Topic",
                "--format",
                "md",
                "--format",
                "pdf",
            ],
        )
        assert result.exit_code == 0

        assert len(list(Path(".").glob("*.md"))) == 1
        assert len(list(Path(".").glob("*.pdf"))) == 1


def test_cli_create_output_path_override(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        # Provide base path, ignoring extension
        result = runner.invoke(
            cli,
            [
                "create",
                "Test Topic",
                "--output",
                "custom_report.txt",
            ],
        )
        assert result.exit_code == 0

        # Should rely on default format (md) but use the custom stem
        expected_file = Path("custom_report.md")
        assert expected_file.exists()


def test_cli_create_with_library_writes_outputs_and_library(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "create",
                "Test Topic",
                "--output",
                "custom_report.md",
                "--library",
                "library",
            ],
        )
        assert result.exit_code == 0, result.output

        assert Path("custom_report.md").read_text(
            encoding="utf-8"
        ) == "# Markdown Content"
        catalog_path = Path("library/catalog.json")
        card_path = Path("library/compendiums/test-title/card.json")
        xml_path = Path("library/compendiums/test-title/compendium.xml")
        markdown_path = Path("library/compendiums/test-title/compendium.md")
        assert catalog_path.exists()
        assert card_path.exists()
        assert xml_path.exists()
        assert markdown_path.exists()

        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        assert catalog["entries"][0]["id"] == "test-title"
        assert catalog["entries"][0]["path"] == (
            "compendiums/test-title/compendium.xml"
        )
        assert markdown_path.read_text(encoding="utf-8") == (
            "# Markdown Content"
        )
        assert "Compendium published to library entry 'test-title'" in (
            result.output
        )


def test_cli_create_html_format_creates_directory(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["create", "Test Topic", "--format", "html"],
        )
        assert result.exit_code == 0

        # Should create a directory, not a single file
        dirs = [d for d in Path(".").iterdir() if d.is_dir()]
        assert len(dirs) == 1
        site_dir = dirs[0]
        assert "test-topic" in site_dir.name

        # Check expected files exist in the directory
        assert (site_dir / "index.html").exists()

        assert (site_dir / "index.html").read_text() == "<html>Index</html>"


def test_cli_recover_uses_research_sidecar(
    runner,
    mock_create_client,
):
    from compendiumscribe.research.agents_workflow import ResearchRunState

    with mock.patch(
        "compendiumscribe.cli.recover_compendium"
    ) as mock_recover:
        compendium = mock.Mock(spec=Compendium)
        compendium.topic = "Recovered"
        compendium.sections = []
        compendium.to_markdown.return_value = "# Recovered"
        mock_recover.return_value = compendium

        with runner.isolated_filesystem():
            state = ResearchRunState(
                topic="Recovered",
                title="Recovered",
                output_formats=["md"],
                cost_report_path="report.costs.json",
            )
            state_path = Path("report.research.json")
            state_path.write_text(
                state.model_dump_json(indent=2),
                encoding="utf-8",
            )

            result = runner.invoke(
                cli,
                ["recover", "--input", str(state_path)],
            )

            assert result.exit_code == 0, result.output
            assert Path("report.md").read_text() == "# Recovered"
            assert Path("report.costs.json").exists()
            mock_recover.assert_called_once()
            assert (
                mock_recover.call_args.kwargs["client"]
                is mock_create_client.return_value
            )


def test_cli_recover_research_failure_exits_nonzero(
    runner,
    mock_create_client,
):
    from compendiumscribe.research.agents_workflow import ResearchRunState

    with mock.patch(
        "compendiumscribe.cli.recover_compendium",
        side_effect=DeepResearchError("Source coverage failed."),
    ):
        with runner.isolated_filesystem():
            state = ResearchRunState(
                topic="Recovered",
                title="Recovered",
                output_formats=["md"],
                cost_report_path="report.costs.json",
            )
            state_path = Path("report.research.json")
            state_path.write_text(
                state.model_dump_json(indent=2),
                encoding="utf-8",
            )

            result = runner.invoke(
                cli,
                ["recover", "--input", str(state_path)],
            )

            assert result.exit_code == 1
            assert "Source coverage failed." in result.output


def test_cli_library_import_writes_catalog_and_compendium_files(
    runner,
):
    with runner.isolated_filesystem():
        xml_path = Path("existing.xml")
        xml_path.write_text(
            """<compendium topic="Imported Topic">
  <overview>Imported overview.</overview>
  <sections>
    <section id="s1">
      <title>Imported Section</title>
      <summary>Imported summary.</summary>
    </section>
  </sections>
</compendium>""",
            encoding="utf-8",
        )

        result = runner.invoke(
            cli,
            ["library", "import", "library", str(xml_path)],
        )

        assert result.exit_code == 0, result.output
        assert "Imported 'Imported Topic' as library entry" in result.output
        catalog = json.loads(
            Path("library/catalog.json").read_text(encoding="utf-8")
        )
        assert catalog["entries"][0]["id"] == "imported-topic"
        assert Path(
            "library/compendiums/imported-topic/compendium.xml"
        ).exists()
        assert Path(
            "library/compendiums/imported-topic/compendium.md"
        ).exists()
        assert Path("library/compendiums/imported-topic/card.json").exists()

        second = runner.invoke(
            cli,
            ["library", "import", "library", str(xml_path)],
        )
        assert second.exit_code == 0, second.output
        catalog = json.loads(
            Path("library/catalog.json").read_text(encoding="utf-8")
        )
        assert len(catalog["entries"]) == 1


def test_cli_render_html(tmp_path):
    """Verify render subcommand creates an HTML site from XML."""
    runner = CliRunner()

    # create dummy XML file
    xml_content = """<compendium topic="Test Topic">
  <overview>Overview content</overview>
  <sections>
    <section id="s1">
      <title>Section 1</title>
      <summary>Summary 1</summary>
    </section>
  </sections>
</compendium>"""
    input_file = tmp_path / "test.xml"
    input_file.write_text(xml_content, encoding="utf-8")

    # Run CLI
    result = runner.invoke(
        cli,
        ["render", str(input_file), "--format", "html"],
    )

    assert result.exit_code == 0, result.output
    assert "Reading compendium from" in result.output
    assert "HTML site written to" in result.output

    # Check output
    site_dir = tmp_path / "test"
    assert site_dir.is_dir()
    assert (site_dir / "index.html").exists()
    assert (site_dir / "sections/s1.html").exists()


def test_cli_render_markdown(tmp_path):
    """Verify render subcommand creates a Markdown file from XML."""
    runner = CliRunner()

    xml_content = """<compendium topic="MD Test">
  <overview>Markdown Overview</overview>
</compendium>"""
    input_file = tmp_path / "md_test.xml"
    input_file.write_text(xml_content, encoding="utf-8")

    # Run CLI
    result = runner.invoke(
        cli,
        ["render", str(input_file), "--format", "md"],
    )

    assert result.exit_code == 0, result.output

    # Check output
    output_file = tmp_path / "md_test.md"
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "# MD Test" in content
    assert "Markdown Overview" in content


def test_cli_render_invalid_file(tmp_path):
    """Verify render subcommand handles non-existent or invalid files."""
    runner = CliRunner()

    # Non-existent file - handled by click type=Path(exists=True)
    result = runner.invoke(cli, ["render", str(tmp_path / "missing.xml")])
    assert result.exit_code != 0
    assert "Invalid value for 'INPUT_FILE'" in result.output

    # Invalid XML content
    invalid_file = tmp_path / "invalid.xml"
    invalid_file.write_text("Not XML", encoding="utf-8")

    result = runner.invoke(cli, ["render", str(invalid_file)])
    assert result.exit_code != 0
    assert "Error parsing XML file" in result.output
