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
    with mock.patch("compendiumscribe.cli.create_openai_client") as mock_client:
        yield mock_client

def test_cli_create_default_format_is_markdown(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["create", "Test Topic", "--no-background"])
        assert result.exit_code == 0, result.output
        
        # Should generate a markdown file by default
        files = list(Path(".").glob("*.md"))
        assert len(files) == 1
        assert "test-topic" in files[0].name
        assert files[0].read_text() == "# Markdown Content"

def test_cli_create_format_xml(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["create", "Test Topic", "--format", "xml", "--no-background"])
        assert result.exit_code == 0
        
        files = list(Path(".").glob("*.xml"))
        assert len(files) == 1
        assert files[0].read_text() == "<xml>Content</xml>"

def test_cli_create_multiple_formats(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["create", "Test Topic", "--format", "md", "--format", "pdf", "--no-background"])
        assert result.exit_code == 0
        
        assert len(list(Path(".").glob("*.md"))) == 1
        assert len(list(Path(".").glob("*.pdf"))) == 1

def test_cli_create_output_path_override(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        # Provide base path, ignoring extension
        result = runner.invoke(cli, ["create", "Test Topic", "--output", "custom_report.txt", "--no-background"])
        assert result.exit_code == 0
        
        # Should rely on default format (md) but use the custom stem
        expected_file = Path("custom_report.md")
        assert expected_file.exists()


def test_cli_create_html_format_creates_directory(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["create", "Test Topic", "--format", "html", "--no-background"])
        assert result.exit_code == 0
        
        # Should create a directory, not a single file
        dirs = [d for d in Path(".").iterdir() if d.is_dir()]
        assert len(dirs) == 1
        site_dir = dirs[0]
        assert "test-topic" in site_dir.name
        
        # Check expected files exist in the directory
        assert (site_dir / "index.html").exists()

        assert (site_dir / "index.html").read_text() == "<html>Index</html>"


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
    result = runner.invoke(cli, ["render", str(input_file), "--format", "html"])
    
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
    result = runner.invoke(cli, ["render", str(input_file), "--format", "md"])
    
    assert result.exit_code == 0, result.output
    
    # Check output
    output_file = tmp_path / "md_test.md"
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "# MD Test" in content
    assert "Markdown Overview" in content


def test_cli_render_invalid_file(tmp_path):
    """Verify render subcommand handles non-existent or invalid files gracefully."""
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
