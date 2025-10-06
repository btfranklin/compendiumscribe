from __future__ import annotations

from compendiumscribe.research.planning import (
    compose_deep_research_prompt,
    strip_leading_markdown_header,
)


def test_strip_leading_markdown_header_removes_heading():
    prompt = """# Title\n\n## Subtitle\n\nDo things."""

    assert strip_leading_markdown_header(prompt).startswith("## Subtitle")


def test_compose_deep_research_prompt_uses_plan_details():
    plan = {
        "primary_objective": "Understand the domain",
        "audience": "Analysts",
        "key_sections": [{"title": "Foundations", "focus": "History"}],
        "research_questions": ["What started the field?"],
        "methodology_preferences": ["Prioritize peer-reviewed sources."],
    }

    prompt = compose_deep_research_prompt("Sample Topic", plan)

    assert "Sample Topic" in prompt
    assert "Foundations" in prompt
    assert "What started the field?" in prompt
    assert "schema" in prompt
    assert not prompt.lstrip().startswith("#")
