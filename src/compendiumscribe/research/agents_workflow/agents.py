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
from contract4agents.target_bindings import load_target_bindings


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
            profile=config.contract4agents_profile,
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


def selected_profile_agent_model(profile: str, agent_name: str) -> str:
    contract_root = files("compendiumscribe.agent_contracts")
    with as_file(contract_root) as root:
        return _selected_profile_agent_model(Path(root), profile, agent_name)


def _selected_profile_agent_model(
    root: Path,
    profile: str,
    agent_name: str,
) -> str:
    loaded = load_target_bindings(root, required=True)
    if loaded.bindings is None or not loaded.ok:
        details = "; ".join(item.message for item in loaded.diagnostics)
        raise RuntimeError(
            details or f"Could not load target bindings from {loaded.path}"
        )

    target = loaded.bindings.targets.get("openai")
    selected = target.profiles.get(profile) if target is not None else None
    if selected is None:
        raise RuntimeError(f"Unknown Contract4Agents OpenAI profile: {profile}")
    agent_profile = selected.agents.get(agent_name)
    model = agent_profile.model if agent_profile is not None else None
    model = model or selected.default_model
    if not model:
        raise RuntimeError(
            f"Contract4Agents profile {profile!r} has no model for {agent_name}."
        )
    return model


__all__ = [
    "ResearchAgentTeam",
    "build_research_agent_team",
    "selected_profile_agent_model",
]
