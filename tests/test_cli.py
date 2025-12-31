import json
import pytest
from click.testing import CliRunner
from pathlib import Path
from unittest import mock
from compendiumscribe.cli import cli
from compendiumscribe.compendium import Compendium


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_build_compendium():
    with mock.patch("compendiumscribe.cli.build_compendium") as mock_build:
        compendium = mock.Mock(spec=Compendium)
        compendium.topic = "Test Title"
        compendium.overview = "Overview text."
        compendium.sections = []
        compendium.to_markdown.return_value = "# Markdown Content"
        compendium.to_xml_string.return_value = "<xml>Content</xml>"
        compendium.to_html_site.return_value = {
            "index.html": "<html>Index</html>",
        }
        compendium.to_pdf_bytes.return_value = b"PDF Content"
        mock_build.return_value = compendium
        yield mock_build


@pytest.fixture
def mock_create_client():
    with mock.patch(
        "compendiumscribe.cli.create_openai_client"
    ) as mock_client:
        yield mock_client


class DummyResponses:
    def __init__(self, payloads: list[dict[str, str]]):
        self._payloads = list(payloads)

    def create(self, **_kwargs):
        if not self._payloads:
            raise RuntimeError("No more responses configured.")
        return self._payloads.pop(0)


class DummyClient:
    def __init__(self, payloads: list[dict[str, str]]):
        self.responses = DummyResponses(payloads)


def test_cli_create_default_format_is_markdown(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["create", "Test Topic", "--no-background"],
        )
        assert result.exit_code == 0, result.output

        # Should generate a markdown file by default
        files = list(Path(".").glob("*.md"))
        assert len(files) == 1
        assert "test-title" in files[0].name
        assert files[0].read_text() == "# Markdown Content"


def test_cli_create_format_xml(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["create", "Test Topic", "--format", "xml", "--no-background"],
        )
        assert result.exit_code == 0

        files = list(Path(".").glob("*.xml"))
        assert len(files) == 1
        assert files[0].read_text() == "<xml>Content</xml>"


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
                "--no-background",
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
                "--no-background",
            ],
        )
        assert result.exit_code == 0

        # Should rely on default format (md) but use the custom stem
        expected_file = Path("custom_report.md")
        assert expected_file.exists()


def test_cli_create_html_format_creates_directory(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["create", "Test Topic", "--format", "html", "--no-background"],
        )
        assert result.exit_code == 0

        # Should create a directory, not a single file
        dirs = [d for d in Path(".").iterdir() if d.is_dir()]
        assert len(dirs) == 1
        site_dir = dirs[0]
        assert "test-title" in site_dir.name

        # Check expected files exist in the directory
        assert (site_dir / "index.html").exists()

        assert (site_dir / "index.html").read_text() == "<html>Index</html>"


def test_cli_create_skill_format(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    name_payload = {
        "name": "test-skill",
        "description": "Use when analyzing test topics.",
    }
    skill_markdown = (
        "---\n"
        "name: test-skill\n"
        "description: Use when analyzing test topics.\n"
        "---\n\n"
        "Read `references/report.md` before responding.\n"
    )
    payloads = [
        {"output_text": json.dumps(name_payload)},
        {"output_text": json.dumps({"skill_markdown": skill_markdown})},
    ]
    mock_create_client.return_value = DummyClient(payloads)

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "create",
                "Test Topic",
                "--format",
                "skill",
                "--output",
                "report.md",
                "--no-background",
            ],
        )
        assert result.exit_code == 0, result.output

        skill_dir = Path("test-skill")
        assert skill_dir.is_dir()
        skill_file = skill_dir / "SKILL.md"
        assert skill_file.read_text(encoding="utf-8") == skill_markdown

        references = list((skill_dir / "references").glob("*.md"))
        assert len(references) == 1
        assert references[0].name == "report.md"
        assert references[0].read_text() == "# Markdown Content"


def test_cli_create_skill_failure_writes_markdown(
    runner,
    mock_build_compendium,
    mock_create_client,
):
    payloads = [
        {"output_text": "not json"},
        {"output_text": "still not json"},
        {"output_text": "nope"},
    ]
    mock_create_client.return_value = DummyClient(payloads)

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "create",
                "Test Topic",
                "--format",
                "skill",
                "--no-background",
            ],
        )
        assert result.exit_code != 0

        markdown_files = list(Path(".").glob("*.md"))
        assert len(markdown_files) == 1
        assert markdown_files[0].read_text() == "# Markdown Content"
        assert "Skill generation failed" in result.output


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


def test_cli_render_skill(tmp_path, mock_create_client):
    """Verify render subcommand creates a skill folder from XML."""
    runner = CliRunner()

    xml_content = """<compendium topic="Skill Topic">
  <overview>Overview content</overview>
</compendium>"""
    input_file = tmp_path / "skill_test.xml"
    input_file.write_text(xml_content, encoding="utf-8")

    name_payload = {
        "name": "skill-builder",
        "description": "Build skills from structured research.",
    }
    skill_markdown = (
        "---\n"
        "name: skill-builder\n"
        "description: Build skills from structured research.\n"
        "---\n\n"
        "Read `references/skill_test.md` before responding.\n"
    )
    payloads = [
        {"output_text": json.dumps(name_payload)},
        {"output_text": json.dumps({"skill_markdown": skill_markdown})},
    ]
    mock_create_client.return_value = DummyClient(payloads)

    result = runner.invoke(
        cli,
        ["render", str(input_file), "--format", "skill"],
    )

    assert result.exit_code == 0, result.output
    skill_dir = tmp_path / "skill-builder"
    assert skill_dir.is_dir()
    assert (skill_dir / "SKILL.md").read_text(
        encoding="utf-8"
    ) == skill_markdown
    assert (
        skill_dir / "references" / "skill_test.md"
    ).exists()


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
