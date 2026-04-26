from __future__ import annotations

from importlib.resources import files
from typing import Any

from .artifacts import (
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    SectionResearchBrief,
    VerificationReport,
)


def create_planner_agent(config: Any):
    from agents import Agent

    return Agent(
        name="PlannerAgent",
        instructions=_load_prompt("planner_agent.prompt.md"),
        model=config.planner_agent_model,
        output_type=ResearchPlan,
    )


def create_research_manager_agent(config: Any):
    from agents import Agent, WebSearchTool

    return Agent(
        name="ResearchManagerAgent",
        instructions=_load_prompt("research_manager_agent.prompt.md"),
        model=config.research_agent_model,
        tools=[WebSearchTool(search_context_size="medium")],
        output_type=ResearchAgenda,
    )


def create_section_research_agent(config: Any):
    from agents import Agent, WebSearchTool

    return Agent(
        name="SectionResearchAgent",
        instructions=_load_prompt("section_research_agent.prompt.md"),
        model=config.research_agent_model,
        tools=[WebSearchTool(search_context_size="high")],
        output_type=SectionResearchBrief,
    )


def create_verifier_agent(config: Any):
    from agents import Agent, WebSearchTool

    return Agent(
        name="VerifierAgent",
        instructions=_load_prompt("verifier_agent.prompt.md"),
        model=config.verifier_agent_model,
        tools=[WebSearchTool(search_context_size="medium")],
        output_type=VerificationReport,
    )


def create_synthesis_agent(config: Any):
    from agents import Agent

    return Agent(
        name="SynthesisAgent",
        instructions=_load_prompt("synthesis_agent.prompt.md"),
        model=config.synthesis_agent_model,
        output_type=CompendiumPayload,
    )


def _load_prompt(filename: str) -> str:
    return (
        files("compendiumscribe.prompts")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


__all__ = [
    "create_planner_agent",
    "create_research_manager_agent",
    "create_section_research_agent",
    "create_synthesis_agent",
    "create_verifier_agent",
]
