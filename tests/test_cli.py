import os
from contextlib import chdir
import pytest
from click.testing import CliRunner
from datetime import datetime, timezone
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
        compendium.generated_at = datetime(
            2026, 7, 22, 12, 0, tzinfo=timezone.utc
        )
        compendium.to_okf_bundle.return_value = Compendium(
            topic="Test Title",
            overview="Overview text.",
            sections=compendium.sections,
            citations=compendium.citations,
            generated_at=compendium.generated_at,
        ).to_okf_bundle()
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


def test_cli_create_default_format_is_okf(
    runner,
    mock_build_compendium,
    mock_create_client,
    tmp_path,
):
    with chdir(tmp_path):
        result = runner.invoke(
            cli,
            ["create", "Test Topic"],
        )
        assert result.exit_code == 0, result.output

        bundles = list(Path(".").glob("*.okf"))
        assert len(bundles) == 1
        assert "test-topic" in bundles[0].name
        assert (bundles[0] / "compendium.md").exists()
        assert len(list(Path(".").glob("*.research.json"))) == 1
        assert len(list(Path(".").glob("*.costs.json"))) == 1
        assert not Path("compendiums").exists()
        assert (
            mock_build_compendium.call_args.kwargs["client"]
            is mock_create_client.return_value
        )


def test_cli_create_reports_unknown_profile_as_configuration_error(
    runner,
    mock_create_client,
    tmp_path,
) -> None:
    with mock.patch.dict(
        os.environ,
        {"CONTRACT4AGENTS_PROFILE": "missing"},
    ):
        with chdir(tmp_path):
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
    tmp_path,
):
    with chdir(tmp_path):
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
    tmp_path,
):
    with chdir(tmp_path):
        result = runner.invoke(
            cli,
            [
                "create",
                "Test Topic",
                "--format",
                "okf",
                "--format",
                "html",
                "--format",
                "pdf",
            ],
        )
        assert result.exit_code == 0

        assert len(list(Path(".").glob("*.okf"))) == 1
        assert len(list(Path(".").glob("*/index.html"))) == 1
        assert len(list(Path(".").glob("*.pdf"))) == 1


def test_cli_create_output_path_override(
    runner,
    mock_build_compendium,
    mock_create_client,
    tmp_path,
):
    with chdir(tmp_path):
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

        expected_bundle = Path("custom_report.okf")
        assert expected_bundle.is_dir()


def test_cli_create_with_library_writes_outputs_and_library(
    runner,
    mock_build_compendium,
    mock_create_client,
    tmp_path,
):
    with chdir(tmp_path):
        result = runner.invoke(
            cli,
            [
                "create",
                "Test Topic",
                "--output",
                "custom_report",
                "--library",
                "library",
            ],
        )
        assert result.exit_code == 0, result.output

        assert Path("custom_report.okf/compendium.md").exists()
        assert Path("library/index.md").exists()
        assert Path("library/compendiums/index.md").exists()
        assert Path(
            "library/compendiums/test-title/compendium.md"
        ).exists()
        assert "Compendium published to library entry 'test-title'" in (
            result.output
        )


def test_cli_create_html_format_creates_directory(
    runner,
    mock_build_compendium,
    mock_create_client,
    tmp_path,
):
    with chdir(tmp_path):
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
    tmp_path,
):
    from compendiumscribe.research.agents_workflow import ResearchRunState

    with mock.patch(
        "compendiumscribe.cli.recover_compendium"
    ) as mock_recover:
        compendium = mock.Mock(spec=Compendium)
        compendium.topic = "Recovered"
        compendium.overview = "Recovered overview."
        compendium.methodology = []
        compendium.sections = []
        compendium.citations = []
        compendium.open_questions = []
        compendium.generated_at = datetime(
            2026, 7, 22, 12, 0, tzinfo=timezone.utc
        )
        compendium.to_okf_bundle.return_value = Compendium(
            topic="Recovered",
            overview="Recovered overview.",
            generated_at=compendium.generated_at,
        ).to_okf_bundle()
        mock_recover.return_value = compendium

        with chdir(tmp_path):
            state = ResearchRunState(
                topic="Recovered",
                title="Recovered",
                output_formats=["okf"],
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
            assert Path("report.okf/compendium.md").exists()
            assert Path("report.costs.json").exists()
            mock_recover.assert_called_once()
            assert (
                mock_recover.call_args.kwargs["client"]
                is mock_create_client.return_value
            )


def test_cli_recover_research_failure_exits_nonzero(
    runner,
    mock_create_client,
    tmp_path,
):
    from compendiumscribe.research.agents_workflow import ResearchRunState

    with mock.patch(
        "compendiumscribe.cli.recover_compendium",
        side_effect=DeepResearchError("Source coverage failed."),
    ):
        with chdir(tmp_path):
            state = ResearchRunState(
                topic="Recovered",
                title="Recovered",
                output_formats=["okf"],
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


def test_cli_library_import_converts_xml_to_okf(
    runner,
    tmp_path,
):
    with chdir(tmp_path):
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
        assert Path(
            "library/compendiums/imported-topic/compendium.md"
        ).exists()
        assert Path(
            "library/compendiums/imported-topic/sections/s1.md"
        ).exists()
        assert not list(Path("library").rglob("*.xml"))
        assert not list(Path("library").rglob("*.json"))

        second = runner.invoke(
            cli,
            ["library", "import", "library", str(xml_path)],
        )
        assert second.exit_code == 0, second.output
        assert len(
            [
                path
                for path in Path("library/compendiums").iterdir()
                if path.is_dir()
            ]
        ) == 1


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


def test_cli_render_okf(tmp_path):
    """Verify render subcommand creates an OKF bundle from XML."""
    runner = CliRunner()

    xml_content = """<compendium topic="MD Test">
  <overview>OKF Overview</overview>
</compendium>"""
    input_file = tmp_path / "md_test.xml"
    input_file.write_text(xml_content, encoding="utf-8")

    # Run CLI
    result = runner.invoke(
        cli,
        ["render", str(input_file), "--format", "okf"],
    )

    assert result.exit_code == 0, result.output

    # Check output
    output_bundle = tmp_path / "md_test.okf"
    assert output_bundle.is_dir()
    content = (output_bundle / "compendium.md").read_text(encoding="utf-8")
    assert "title: MD Test" in content
    assert "OKF Overview" in content


def test_cli_render_invalid_file(tmp_path):
    """Verify render subcommand handles non-existent or invalid files."""
    runner = CliRunner()

    # Non-existent file - handled by click type=Path(exists=True)
    result = runner.invoke(cli, ["render", str(tmp_path / "missing.xml")])
    assert result.exit_code != 0
    assert "Invalid value for 'INPUT_PATH'" in result.output

    # Invalid XML content
    invalid_file = tmp_path / "invalid.xml"
    invalid_file.write_text("Not XML", encoding="utf-8")

    result = runner.invoke(cli, ["render", str(invalid_file)])
    assert result.exit_code != 0
    assert "Error parsing compendium" in result.output


def test_cli_rejects_removed_markdown_format(runner) -> None:
    result = runner.invoke(
        cli,
        ["create", "Test Topic", "--format", "md"],
    )

    assert result.exit_code != 0
    assert "Invalid value for '--format'" in result.output


def test_cli_recovery_rejects_removed_markdown_state(
    runner,
    mock_create_client,
    tmp_path,
) -> None:
    from compendiumscribe.research.agents_workflow import ResearchRunState

    with chdir(tmp_path):
        state = ResearchRunState(topic="Legacy", output_formats=["md"])
        state_path = Path("legacy.research.json")
        state_path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )

        result = runner.invoke(
            cli,
            ["recover", "--input", str(state_path)],
        )

        assert result.exit_code == 1
        assert "unsupported output format(s): md" in result.output


def test_cli_renders_okf_input_to_xml_and_refuses_self_overwrite(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "source.okf"
    from compendiumscribe.compendium import write_okf_bundle

    compendium = Compendium(topic="OKF Source", overview="Overview.")
    write_okf_bundle(bundle_path, compendium.to_okf_bundle())

    result = CliRunner().invoke(
        cli,
        ["render", str(bundle_path), "--format", "xml"],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "source.xml").exists()

    overwrite = CliRunner().invoke(
        cli,
        ["render", str(bundle_path), "--format", "okf"],
    )
    assert overwrite.exit_code != 0
    assert "Refusing to overwrite the input OKF bundle" in overwrite.output


def test_cli_library_validate(tmp_path: Path) -> None:
    from compendiumscribe.library import publish_compendium

    library_path = tmp_path / "library"
    publish_compendium(
        Compendium(topic="Valid", overview="Overview."),
        library_path,
    )

    result = CliRunner().invoke(
        cli,
        ["library", "validate", str(library_path)],
    )

    assert result.exit_code == 0
    assert "Library is valid" in result.output
