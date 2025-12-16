import pytest
from click.testing import CliRunner
from pathlib import Path
from unittest import mock
from compendiumscribe.cli import main
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
        compendium.to_html.return_value = "<html>Content</html>"
        compendium.to_html_site.return_value = {
            "index.html": "<html>Index</html>",
            "style.css": "/* styles */",
        }
        compendium.to_pdf_bytes.return_value = b"PDF Content"
        mock_build.return_value = compendium
        yield mock_build

@pytest.fixture
def mock_create_client():
    with mock.patch("compendiumscribe.cli.create_openai_client") as mock_client:
        yield mock_client

def test_cli_default_format_is_markdown(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["Test Topic", "--no-background"])
        assert result.exit_code == 0, result.output
        
        # Should generate a markdown file by default
        files = list(Path(".").glob("*.md"))
        assert len(files) == 1
        assert "test-topic" in files[0].name
        assert files[0].read_text() == "# Markdown Content"

def test_cli_format_xml(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["Test Topic", "--format", "xml", "--no-background"])
        assert result.exit_code == 0
        
        files = list(Path(".").glob("*.xml"))
        assert len(files) == 1
        assert files[0].read_text() == "<xml>Content</xml>"

def test_cli_multiple_formats(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["Test Topic", "--format", "md", "--format", "pdf", "--no-background"])
        assert result.exit_code == 0
        
        assert len(list(Path(".").glob("*.md"))) == 1
        assert len(list(Path(".").glob("*.pdf"))) == 1

def test_cli_output_path_override(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        # Provide base path, ignoring extension
        result = runner.invoke(main, ["Test Topic", "--output", "custom_report.txt", "--no-background"])
        assert result.exit_code == 0
        
        # Should rely on default format (md) but use the custom stem
        expected_file = Path("custom_report.md")
        assert expected_file.exists()


def test_cli_html_format_creates_directory(runner, mock_build_compendium, mock_create_client):
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["Test Topic", "--format", "html", "--no-background"])
        assert result.exit_code == 0
        
        # Should create a directory, not a single file
        dirs = [d for d in Path(".").iterdir() if d.is_dir()]
        assert len(dirs) == 1
        site_dir = dirs[0]
        assert "test-topic" in site_dir.name
        
        # Check expected files exist in the directory
        assert (site_dir / "index.html").exists()
        assert (site_dir / "style.css").exists()
        assert (site_dir / "index.html").read_text() == "<html>Index</html>"
