from __future__ import annotations

from importlib.resources import files

from compendiumscribe.research.agents_workflow.agents import _load_prompt


RESEARCH_PROMPTS = {
    "planner_agent.prompt.md",
    "research_manager_agent.prompt.md",
    "section_research_agent.prompt.md",
    "verifier_agent.prompt.md",
    "synthesis_agent.prompt.md",
}


def test_research_prompts_load_from_package() -> None:
    for prompt_name in RESEARCH_PROMPTS:
        prompt = _load_prompt(prompt_name)
        normalized = " ".join(prompt.split())
        assert prompt.startswith("# ")
        assert "structured output requested by the runtime" in normalized


def test_prompt_package_contains_research_agent_prompts() -> None:
    prompt_names = {
        prompt_path.name
        for prompt_path in files("compendiumscribe.prompts").iterdir()
        if prompt_path.name.endswith(".prompt.md")
    }

    assert prompt_names == RESEARCH_PROMPTS
