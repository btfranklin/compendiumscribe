from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from contract4agents.compiler import CompilerArtifacts, compile_project
from contract4agents.materialization import (
    MaterializationTraceEvent,
    RecordingTraceSink,
    materialize,
)
from contract4agents.planning import MaterializationPlan
from contract4agents.target_bindings import (
    AgentProfile,
    TargetBinding,
    TargetBindings,
    TargetProfile,
    load_target_bindings,
)


@dataclass(frozen=True)
class ResearchAgentTeam:
    planner: Any
    research_manager: Any
    section_research: Any
    verifier: Any
    synthesis: Any
    artifacts: CompilerArtifacts
    plan: MaterializationPlan
    materialization_events: tuple[MaterializationTraceEvent, ...]


def build_research_agent_team(config: Any) -> ResearchAgentTeam:
    """Materialize the complete native OpenAI graph from packaged contracts."""

    contract_root = files("compendiumscribe.agent_contracts")
    with as_file(contract_root) as root:
        root_path = Path(root)
        artifacts = compile_project(root_path)
        trace_sink = RecordingTraceSink()
        result = materialize(
            root_path,
            target="openai",
            profile="runtime",
            bindings=_runtime_bindings(root_path, config),
            trace_sink=trace_sink,
        )

    return ResearchAgentTeam(
        planner=result.agents["PlannerAgent"],
        research_manager=result.agents["ResearchManagerAgent"],
        section_research=result.agents["SectionResearchAgent"],
        verifier=result.agents["VerifierAgent"],
        synthesis=result.agents["SynthesisAgent"],
        artifacts=artifacts,
        plan=result.plan,
        materialization_events=tuple(trace_sink.events),
    )


def _runtime_bindings(root: Path, config: Any) -> TargetBindings:
    loaded = load_target_bindings(root, required=True)
    if loaded.bindings is None or not loaded.ok:
        details = "; ".join(item.message for item in loaded.diagnostics)
        raise RuntimeError(
            details or f"Could not load target bindings from {loaded.path}"
        )

    declared = loaded.bindings.targets["openai"]
    runtime = TargetProfile(
        default_model=config.research_agent_model,
        agents={
            "PlannerAgent": AgentProfile(model=config.planner_agent_model),
            "ResearchManagerAgent": AgentProfile(model=config.research_agent_model),
            "SectionResearchAgent": AgentProfile(model=config.research_agent_model),
            "VerifierAgent": AgentProfile(model=config.verifier_agent_model),
            "SynthesisAgent": AgentProfile(model=config.synthesis_agent_model),
        },
    )
    target = TargetBinding(
        adapter=declared.adapter,
        tools=declared.tools,
        datasources=declared.datasources,
        external_context=declared.external_context,
        environments=declared.environments,
        profiles={**declared.profiles, "runtime": runtime},
    )
    return TargetBindings(
        path=loaded.bindings.path,
        schema_version=loaded.bindings.schema_version,
        targets={"openai": target},
    )


__all__ = [
    "ResearchAgentTeam",
    "build_research_agent_team",
]
