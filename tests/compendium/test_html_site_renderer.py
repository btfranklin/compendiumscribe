"""Tests for the HTML site renderer."""

from __future__ import annotations

from compendiumscribe.compendium import (
    Citation,
    Compendium,
    Insight,
    Section,
)


def _sample_compendium() -> Compendium:
    """Create a sample compendium for testing."""
    return Compendium(
        topic="Test Topic",
        overview="This is the overview.",
        methodology=["Step 1", "Step 2"],
        sections=[
            Section(
                identifier="S1",
                title="First Section",
                summary="Summary of section one.",
                key_terms=["term1", "term2"],
                guiding_questions=["What is this?"],
                insights=[
                    Insight(
                        title="Key Insight",
                        evidence="Evidence text here.",
                        implications="Potential implications.",
                        citation_refs=["C1"],
                    )
                ],
            ),
            Section(
                identifier="S2",
                title="Second Section",
                summary="Summary of section two.",
            ),
        ],
        citations=[
            Citation(
                identifier="C1",
                title="Source Title",
                url="https://example.com/source",
                publisher="Publisher Inc",
                published_at="2024-01-15",
                summary="Source summary.",
            )
        ],
        open_questions=["What comes next?"],
    )


def test_render_html_site_returns_expected_files():
    """Verify that render_html_site returns all expected file paths."""
    compendium = _sample_compendium()
    files = compendium.to_html_site()

    expected_keys = {
        "index.html",
        "sections/s1.html",
        "sections/s2.html",
        "citations.html",
        "open-questions.html",
        "style.css",
    }
    assert set(files.keys()) == expected_keys


def test_index_page_has_semantic_structure():
    """Verify index page uses semantic HTML elements."""
    compendium = _sample_compendium()
    files = compendium.to_html_site()
    index = files["index.html"]

    assert "<!DOCTYPE html>" in index
    assert "<header>" in index
    assert "<main>" in index
    assert "<nav>" in index
    assert "<footer>" in index
    assert "Test Topic" in index
    assert "This is the overview." in index


def test_index_page_contains_nav_links():
    """Verify navigation links to all sections and pages."""
    compendium = _sample_compendium()
    files = compendium.to_html_site()
    index = files["index.html"]

    assert 'href="sections/s1.html"' in index
    assert 'href="sections/s2.html"' in index
    assert 'href="citations.html"' in index
    assert 'href="open-questions.html"' in index


def test_section_pages_have_semantic_structure():
    """Verify section pages use semantic HTML and have proper content."""
    compendium = _sample_compendium()
    files = compendium.to_html_site()
    section_page = files["sections/s1.html"]

    assert "<!DOCTYPE html>" in section_page
    assert "<header>" in section_page
    assert "<main>" in section_page
    assert "<article>" in section_page  # For insights
    assert "First Section" in section_page
    assert "Summary of section one." in section_page
    assert "term1" in section_page
    assert "Key Insight" in section_page
    assert "Evidence text here." in section_page


def test_section_pages_link_back_to_index():
    """Verify section pages have navigation back to home."""
    compendium = _sample_compendium()
    files = compendium.to_html_site()
    section_page = files["sections/s1.html"]

    assert 'href="../index.html"' in section_page


def test_citations_page_lists_all_citations():
    """Verify citations page contains all citation details."""
    compendium = _sample_compendium()
    files = compendium.to_html_site()
    citations = files["citations.html"]

    assert "Citations" in citations
    assert "Source Title" in citations
    assert "https://example.com/source" in citations
    assert "Publisher Inc" in citations
    assert "2024-01-15" in citations


def test_open_questions_page_lists_all_questions():
    """Verify open questions page contains all questions."""
    compendium = _sample_compendium()
    files = compendium.to_html_site()
    questions = files["open-questions.html"]

    assert "Open Questions" in questions
    assert "What comes next?" in questions


def test_empty_compendium_handles_gracefully():
    """Verify empty compendium generates valid pages."""
    compendium = Compendium(
        topic="Empty Topic",
        overview="Just an overview.",
    )
    files = compendium.to_html_site()

    assert "index.html" in files
    assert "citations.html" in files
    assert "open-questions.html" in files
    # No section files since no sections
    assert not any(k.startswith("sections/") for k in files.keys())

    # Pages should still be valid HTML
    assert "<!DOCTYPE html>" in files["index.html"]
    assert "No citations available" in files["citations.html"]
    assert "No open questions recorded" in files["open-questions.html"]


def test_style_css_is_valid():
    """Verify style.css is included and contains minimal styles."""
    compendium = _sample_compendium()
    files = compendium.to_html_site()
    css = files["style.css"]

    assert "box-sizing" in css
    assert "font-family" in css
