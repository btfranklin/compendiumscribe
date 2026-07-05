from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import as_file, files
from typing import Any

from contract4agents.adapters.openai import build_openai_agents_from_contracts
from contract4agents.compiler import CompilerArtifacts, compile_project

from .artifacts import (
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    SectionResearchBrief,
    VerificationReport,
)


@dataclass(frozen=True)
class ResearchAgentTeam:
    planner: Any
    research_manager: Any
    section_research: Any
    verifier: Any
    synthesis: Any
    artifacts: CompilerArtifacts


def build_research_agent_team(config: Any) -> ResearchAgentTeam:
    result = build_openai_agents_from_contracts(
        _compiled_contracts(),
        output_type_registry={
            "CompendiumPayload": CompendiumPayload,
            "ResearchAgenda": ResearchAgenda,
            "ResearchPlan": ResearchPlan,
            "SectionResearchBrief": SectionResearchBrief,
            "VerificationReport": VerificationReport,
        },
        model_registry={
            "PlannerAgent": config.planner_agent_model,
            "ResearchManagerAgent": config.research_agent_model,
            "SectionResearchAgent": config.research_agent_model,
            "VerifierAgent": config.verifier_agent_model,
            "SynthesisAgent": config.synthesis_agent_model,
        },
        hosted_tool_registry={"openai.web_search": True},
        instruction_overrides=_instruction_overrides(),
    )
    if result.caveats:
        details = "; ".join(
            f"{caveat.agent}: {caveat.kind}: {caveat.message}"
            for caveat in result.caveats
        )
        raise RuntimeError(
            f"Contract4Agents adapter caveats are not allowed: {details}"
        )

    return ResearchAgentTeam(
        planner=result.agents["PlannerAgent"],
        research_manager=result.agents["ResearchManagerAgent"],
        section_research=result.agents["SectionResearchAgent"],
        verifier=result.agents["VerifierAgent"],
        synthesis=result.agents["SynthesisAgent"],
        artifacts=result.plan.artifacts,
    )


@lru_cache(maxsize=1)
def _compiled_contracts() -> CompilerArtifacts:
    contract_root = files("compendiumscribe.agent_contracts")
    with as_file(contract_root) as root:
        return compile_project(root, allow_python_imports=True)


def _load_prompt(filename: str) -> str:
    return (
        files("compendiumscribe.prompts")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def _instruction_overrides() -> dict[str, str]:
    return {
        "PlannerAgent": _load_prompt("planner_agent.prompt.md"),
        "ResearchManagerAgent": _load_prompt("research_manager_agent.prompt.md"),
        "SectionResearchAgent": _load_prompt("section_research_agent.prompt.md"),
        "VerifierAgent": _load_prompt("verifier_agent.prompt.md"),
        "SynthesisAgent": _load_prompt("synthesis_agent.prompt.md"),
    }


__all__ = [
    "ResearchAgentTeam",
    "build_research_agent_team",
]
