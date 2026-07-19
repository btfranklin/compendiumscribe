from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeVar

from contract4agents.assurance import assess_controls
from contract4agents.ir import CanonicalIR, semantic_id
from contract4agents.planning import MaterializationPlan
from contract4agents.tracing import (
    NormalizedTrace,
    TraceConformanceError,
    normalize_openai_response_events,
    validate_trace_conformance,
)
from pydantic import BaseModel

from ...compendium import Compendium, slugify
from ..config import ResearchConfig
from ..errors import DeepResearchError
from ..progress import emit_progress
from .agents import ResearchAgentTeam, build_research_agent_team
from ...agent_contracts.generated.python import (
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    SectionResearchBrief,
    VerificationReport,
)
from .artifacts import ResearchRunState, prepare_compendium_payload
from .contract_trace import ContractTraceRecorder
from .costing import record_agent_result_cost
from .runner import AgentRunResult, AgentRunner, OpenAIAgentRunner
from .source_ledger import build_source_ledger, mark_cited_sources
from .state import load_state, save_state

if TYPE_CHECKING:
    from ..costs import CostTracker
    from openai import AsyncOpenAI

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


def build_compendium_with_agents(
    topic: str,
    *,
    client: "AsyncOpenAI | None" = None,
    config: ResearchConfig | None = None,
    runner: AgentRunner | None = None,
    state_path: Path | None = None,
    cost_tracker: "CostTracker | None" = None,
    output_formats: list[str] | tuple[str, ...] = (),
) -> Compendium:
    if not topic or not topic.strip():
        raise ValueError("Topic must be a non-empty string.")

    config = config or ResearchConfig()
    runner = runner or OpenAIAgentRunner(openai_client=client)
    resolved_state_path = state_path or _default_state_path(topic.strip())

    try:
        return asyncio.run(
            _build_compendium_async(
                topic.strip(),
                config=config,
                runner=runner,
                state_path=resolved_state_path,
                cost_tracker=cost_tracker,
                output_formats=list(output_formats),
            )
        )
    except DeepResearchError:
        raise
    except Exception as exc:
        emit_progress(
            config,
            phase="completion",
            status="error",
            message=str(exc),
        )
        raise


def recover_compendium_from_state(
    state_path: Path,
    *,
    client: "AsyncOpenAI | None" = None,
    config: ResearchConfig | None = None,
    runner: AgentRunner | None = None,
    cost_tracker: "CostTracker | None" = None,
) -> Compendium:
    state = load_state(state_path)
    return build_compendium_with_agents(
        state.topic,
        client=client,
        config=config,
        runner=runner,
        state_path=state_path,
        cost_tracker=cost_tracker,
        output_formats=state.output_formats,
    )


async def _build_compendium_async(
    topic: str,
    *,
    config: ResearchConfig,
    runner: AgentRunner,
    state_path: Path,
    cost_tracker: "CostTracker | None",
    output_formats: list[str],
) -> Compendium:
    state_path_existed = state_path.exists()
    team = build_research_agent_team(config)
    state = _load_or_create_state(
        topic=topic,
        state_path=state_path,
        output_formats=output_formats,
        cost_tracker=cost_tracker,
        config=config,
        plan=team.plan,
    )
    trace_path = _contract_trace_path(state_path)
    trace_required = _state_requires_trace(state)
    if trace_required and not trace_path.exists():
        raise DeepResearchError(
            f"Cannot recover progressed research state without trace evidence: "
            f"{trace_path}"
        )
    save_state(state_path, state)
    trace = _contract_trace_recorder(
        trace_path,
        run_id=state.run_id,
        append=state_path_existed and trace_path.exists(),
        team=team,
    )
    if trace_required and not trace.events:
        raise DeepResearchError(
            "Cannot recover progressed research state from an empty trace: "
            f"{trace_path}"
        )
    if trace.events:
        _validate_contract_trace(team.artifacts.ir, team.plan, trace.trace)

    if state.plan is None:
        state.plan = await _run_structured_agent(
            "planning",
            team.planner,
            _planning_input(topic),
            output_type=ResearchPlan,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state=state,
            trace=trace,
            plan=team.plan,
            ir=team.artifacts.ir,
        )
        state.title = state.plan.title
        state.mark_completed("planning")
        save_state(state_path, state)

    if state.agenda is None:
        state.agenda = await _run_structured_agent(
            "research_agenda",
            team.research_manager,
            _research_agenda_input(topic, state),
            output_type=ResearchAgenda,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state=state,
            trace=trace,
            plan=team.plan,
            ir=team.artifacts.ir,
        )
        state.mark_completed("research_agenda")
        save_state(state_path, state)

    await _run_missing_sections(
        state,
        team=team,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
        state_path=state_path,
        trace=trace,
    )
    _rebuild_ledger(state)
    state.mark_completed("source_ledger")
    save_state(state_path, state)

    if state.verification is None:
        state.verification = await _verify(
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            trace=trace,
        )
        state.mark_completed("verification")
        save_state(state_path, state)

    if state.verification.status == "follow_up" and not state.follow_up_done:
        await _run_follow_up_sections(
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state_path=state_path,
            trace=trace,
        )
        _rebuild_ledger(state)
        state.follow_up_done = True
        state.verification = await _verify(
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            trace=trace,
        )
        state.mark_completed("verification_follow_up")
        save_state(state_path, state)

    if state.verification.status != "accepted":
        save_state(state_path, state)
        raise DeepResearchError(_verification_failure_message(state))

    synthesized = False
    if state.final_payload is None:
        state.final_payload = await _run_structured_agent(
            "synthesis",
            team.synthesis,
            _synthesis_input(topic, state),
            output_type=CompendiumPayload,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state=state,
            trace=trace,
            plan=team.plan,
            ir=team.artifacts.ir,
        )
        synthesized = True

    _evaluate_contract_run(team, trace.trace)
    prepared_payload = prepare_compendium_payload(state.final_payload, state.ledger)
    if synthesized:
        state.final_payload = prepared_payload
        state.mark_completed("synthesis")
        save_state(state_path, state)
    elif prepared_payload != state.final_payload:
        state.final_payload = prepared_payload
        save_state(state_path, state)

    emit_progress(
        config,
        phase="completion",
        status="completed",
        message="Compendium payload is complete.",
        metadata={"state_path": str(state_path)},
    )
    return Compendium.from_payload(
        topic=state.title or topic,
        payload=state.final_payload.model_dump(mode="json"),
        generated_at=datetime.now(timezone.utc),
    )


async def _run_missing_sections(
    state: ResearchRunState,
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state_path: Path,
    trace: ContractTraceRecorder,
) -> None:
    for section in state.agenda.sections:
        if section.id in state.section_briefs:
            continue
        state.section_briefs[section.id] = await _run_section_agent(
            section.id,
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            trace=trace,
        )
        state.mark_completed(f"section_research:{section.id}")
        save_state(state_path, state)


async def _run_follow_up_sections(
    state: ResearchRunState,
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state_path: Path,
    trace: ContractTraceRecorder,
) -> None:
    section_ids = _validated_follow_up_section_ids(state)
    for section_id in section_ids:
        state.section_briefs[section_id] = await _run_section_agent(
            section_id,
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            trace=trace,
            follow_up=True,
        )
        state.mark_completed(f"section_follow_up:{section_id}")
        save_state(state_path, state)


async def _run_section_agent(
    section_id: str,
    state: ResearchRunState,
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    trace: ContractTraceRecorder,
    follow_up: bool = False,
) -> SectionResearchBrief:
    section = _agenda_section(state, section_id)
    if section is None:
        raise DeepResearchError(f"Unknown agenda section: {section_id}")
    return await _run_structured_agent(
        "section_research",
        team.section_research,
        _section_research_input(state, section_id, section, follow_up=follow_up),
        output_type=SectionResearchBrief,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
        state=state,
        trace=trace,
        plan=team.plan,
        ir=team.artifacts.ir,
        metadata={"section_id": section_id, "follow_up": follow_up},
    )


async def _verify(
    state: ResearchRunState,
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    trace: ContractTraceRecorder,
):
    return await _run_structured_agent(
        "verification",
        team.verifier,
        _verification_input(state),
        output_type=VerificationReport,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
        state=state,
        trace=trace,
        plan=team.plan,
        ir=team.artifacts.ir,
    )


def _planning_input(topic: str) -> str:
    return _json_prompt({"topic": topic})


def _research_agenda_input(topic: str, state: ResearchRunState) -> str:
    return _json_prompt(
        {
            "topic": topic,
            "plan": state.plan.model_dump(mode="json"),
        }
    )


def _section_research_input(
    state: ResearchRunState,
    section_id: str,
    section: Any,
    *,
    follow_up: bool,
) -> str:
    return _json_prompt(
        {
            "topic": state.title or state.topic,
            "section": section.model_dump(mode="json"),
            "plan": state.plan.model_dump(mode="json"),
            "agenda": state.agenda.model_dump(mode="json"),
            "previous_brief": (
                state.section_briefs.get(section_id).model_dump(mode="json")
                if follow_up and section_id in state.section_briefs
                else None
            ),
            "verification": (
                state.verification.model_dump(mode="json")
                if follow_up and state.verification is not None
                else None
            ),
        }
    )


def _verification_input(state: ResearchRunState) -> str:
    return _json_prompt(
        {
            "topic": state.title or state.topic,
            "plan": state.plan.model_dump(mode="json"),
            "agenda": state.agenda.model_dump(mode="json"),
            "section_briefs": [
                brief.model_dump(mode="json") for brief in state.section_briefs.values()
            ],
            "source_ledger": state.ledger.model_dump(mode="json"),
            "follow_up_available": not state.follow_up_done,
        }
    )


def _synthesis_input(topic: str, state: ResearchRunState) -> str:
    return _json_prompt(
        {
            "topic": state.title or topic,
            "plan": state.plan.model_dump(mode="json"),
            "agenda": state.agenda.model_dump(mode="json"),
            "section_briefs": [
                brief.model_dump(mode="json") for brief in state.section_briefs.values()
            ],
            "source_ledger": state.ledger.model_dump(mode="json"),
            "verification": state.verification.model_dump(mode="json"),
        }
    )


async def _run_structured_agent(
    phase: str,
    agent: Any,
    input_payload: str,
    *,
    output_type: type[ArtifactT],
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state: ResearchRunState,
    trace: ContractTraceRecorder,
    plan: MaterializationPlan,
    ir: CanonicalIR,
    metadata: dict[str, Any] | None = None,
) -> ArtifactT:
    agent_name = str(getattr(agent, "name", phase))
    trace.record(
        "agent.started",
        agent_name=agent_name,
        data={"agent_name": agent_name, "phase": phase},
    )
    emit_progress(
        config,
        phase=phase,
        status="in_progress",
        message=f"Running {agent_name}.",
        metadata=metadata,
    )
    result = await runner.run(
        agent,
        input_payload,
        max_turns=config.max_agent_turns,
    )
    _record_hosted_tool_events(trace, ir, plan, agent_name, result)
    trace.record(
        "agent.completed",
        agent_name=agent_name,
        data={"phase": phase},
        response_ids=result.response_ids,
    )
    record_agent_result_cost(
        cost_tracker,
        phase=phase,
        model=_resolved_agent_model(plan, agent_name),
        result=result,
    )
    state.response_ids[phase] = list(
        dict.fromkeys(state.response_ids.get(phase, []) + result.response_ids)
    )
    artifact = _coerce_artifact(result, output_type)
    trace.record(
        "output.accepted",
        agent_name=agent_name,
        control_ids=(semantic_id("control", agent_name, "output_conformance"),),
        data={"agent_name": agent_name, "output_type": output_type.__name__},
        response_ids=result.response_ids,
    )
    trace.record(
        "stage.completed",
        agent_name=agent_name,
        data={
            "agent_name": agent_name,
            "metadata": metadata or {},
            "output_type": output_type.__name__,
        },
    )
    emit_progress(
        config,
        phase=phase,
        status="completed",
        message=f"Accepted {agent_name} output.",
        metadata=metadata,
    )
    return artifact


def _coerce_artifact(
    result: AgentRunResult,
    output_type: type[ArtifactT],
) -> ArtifactT:
    output = result.final_output
    if isinstance(output, output_type):
        artifact = output
    elif isinstance(output, BaseModel):
        artifact = output_type.model_validate(output.model_dump(mode="json"))
    elif isinstance(output, dict):
        artifact = output_type.model_validate(output)
    elif isinstance(output, str):
        artifact = output_type.model_validate_json(output)
    else:
        artifact = output_type.model_validate(output)
    return artifact


def _record_hosted_tool_events(
    trace: ContractTraceRecorder,
    ir: CanonicalIR,
    plan: MaterializationPlan,
    agent_name: str,
    result: AgentRunResult,
) -> None:
    raw_result = getattr(result, "raw_result", result)
    normalize_openai_response_events(
        plan,
        list(getattr(raw_result, "raw_responses", []) or []),
        agent=agent_name,
        context=trace.context,
        sink=trace,
    )
    _validate_contract_trace(ir, plan, trace.trace)


def _evaluate_contract_run(
    team: ResearchAgentTeam,
    trace: NormalizedTrace,
) -> None:
    _validate_contract_trace(team.artifacts.ir, team.plan, trace)
    results = assess_controls(
        team.artifacts.ir,
        team.plan,
        trace,
    )
    failures = [result for result in results if result.status != "passed"]
    if failures:
        details = "; ".join(
            f"{result.control_id}: {result.status}: {result.reason}"
            for result in failures
        )
        raise DeepResearchError(f"Contract4Agents assurance failed: {details}")


def _validate_contract_trace(
    ir: CanonicalIR,
    plan: MaterializationPlan,
    trace: NormalizedTrace,
) -> None:
    try:
        validate_trace_conformance(ir, plan, trace)
    except TraceConformanceError as exc:
        raise DeepResearchError(
            f"Contract4Agents trace conformance failed: {exc}"
        ) from exc


def _rebuild_ledger(state: ResearchRunState) -> None:
    briefs = list(state.section_briefs.values())
    ledger = build_source_ledger(briefs)
    cited_urls = [
        source_url
        for brief in briefs
        for finding in brief.findings
        for source_url in finding.source_urls
    ]
    state.ledger = mark_cited_sources(ledger, cited_urls)


def _load_or_create_state(
    *,
    topic: str,
    state_path: Path,
    output_formats: list[str],
    cost_tracker: "CostTracker | None",
    config: ResearchConfig,
    plan: MaterializationPlan,
) -> ResearchRunState:
    if state_path.exists():
        state = load_state(state_path)
        recorded_digest = state.config_snapshot.get("plan_digest")
        if recorded_digest is None and not _state_requires_trace(state):
            state.config_snapshot = _plan_snapshot(config, plan)
            return state
        if recorded_digest != plan.plan_digest:
            raise DeepResearchError(
                "Cannot recover research state with a different "
                "Contract4Agents plan digest."
            )
        return state
    return ResearchRunState(
        topic=topic,
        title=topic,
        output_formats=list(output_formats),
        cost_report_path=str(cost_tracker.path) if cost_tracker else None,
        config_snapshot=_plan_snapshot(config, plan),
    )


def _plan_snapshot(
    config: ResearchConfig,
    plan: MaterializationPlan,
) -> dict[str, Any]:
    return {
        **config.runtime_snapshot(),
        "contract_digest": plan.contract_digest,
        "plan_digest": plan.plan_digest,
        "resolved_models": {
            agent.name: agent.model for agent in plan.agents.values()
        },
    }


def _resolved_agent_model(plan: MaterializationPlan, agent_name: str) -> str:
    matches = [
        agent.model for agent in plan.agents.values() if agent.name == agent_name
    ]
    if len(matches) != 1:
        raise DeepResearchError(
            f"Expected one resolved model for {agent_name}, found {len(matches)}."
        )
    return matches[0]


def _json_prompt(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _agenda_section(state: ResearchRunState, section_id: str):
    for section in state.agenda.sections:
        if section.id == section_id:
            return section
    return None


def _validated_follow_up_section_ids(state: ResearchRunState) -> list[str]:
    section_ids = list(state.verification.follow_up_section_ids)
    if not section_ids:
        raise DeepResearchError(
            "Research verification requested follow-up without any section IDs."
        )
    if len(section_ids) != len(set(section_ids)):
        raise DeepResearchError(
            "Research verification requested duplicate follow-up section IDs."
        )
    agenda_ids = {section.id for section in state.agenda.sections}
    unknown = sorted(set(section_ids) - agenda_ids)
    if unknown:
        raise DeepResearchError(
            "Research verification requested unknown follow-up section IDs: "
            + ", ".join(unknown)
        )
    return section_ids


def _state_requires_trace(state: ResearchRunState) -> bool:
    return bool(
        state.completed_stages
        or state.response_ids
        or state.plan is not None
        or state.agenda is not None
        or state.section_briefs
        or state.verification is not None
        or state.final_payload is not None
    )


def _verification_failure_message(state: ResearchRunState) -> str:
    issues = state.verification.issues if state.verification else []
    details = "; ".join(issue.message for issue in issues) or "unspecified"
    if state.verification and state.verification.status == "follow_up":
        return (
            "Research verification requested another follow-up after the bounded "
            f"follow-up cycle was exhausted: {details}"
        )
    return f"Research verification failed: {details}"


def _default_state_path(topic: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(f"{slugify(topic)}_{timestamp}.research.json")


def _contract_trace_path(state_path: Path) -> Path:
    return state_path.with_suffix(".trace.jsonl")


def _contract_trace_recorder(
    path: Path,
    *,
    run_id: str,
    append: bool,
    team: ResearchAgentTeam,
) -> ContractTraceRecorder:
    try:
        return ContractTraceRecorder(
            path,
            run_id=run_id,
            contract_digest=team.plan.contract_digest,
            plan_digest=team.plan.plan_digest,
            append=append,
        )
    except (OSError, ValueError) as exc:
        raise DeepResearchError(
            f"Cannot recover Contract4Agents trace evidence from {path}: {exc}"
        ) from exc


__all__ = [
    "build_compendium_with_agents",
    "recover_compendium_from_state",
]
