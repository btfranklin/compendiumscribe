from compendiumscribe.research.planning import (
    compose_deep_research_prompt,
)


def test_compose_deep_research_prompt_uses_plan_details():
    plan = {
        "primary_objective": "Understand the domain",
        "audience": "Analysts",
        "key_sections": [{"title": "Foundations", "focus": "History"}],
        "research_questions": ["What started the field?"],
        "methodology_preferences": ["Prioritize peer-reviewed sources."],
    }

    prompt = compose_deep_research_prompt("Sample Topic", plan)

    # Prompt is now a list of OpenAI Responses API input messages
    assert isinstance(prompt, list)
    
    # Flatten text content to check for keywords
    all_text = ""
    for msg in prompt:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                all_text += part.get("text", "") + "\n"
        elif isinstance(content, str):
            all_text += content + "\n"

    assert "Sample Topic" in all_text
    assert "Foundations" in all_text
    assert "What started the field?" in all_text
    assert "schema" in all_text
    assert not all_text.strip().startswith("#")
