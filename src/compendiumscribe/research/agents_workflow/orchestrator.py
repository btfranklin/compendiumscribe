from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeVar

from contract4agents.assertions import RunSpecEvaluationResult, evaluate_run_spec
from contract4agents.runtime import TraceRecorder, load_trace_jsonl
from pydantic import BaseModel

from ...compendium import Compendium, slugify
from ..config import ResearchConfig
from ..costs import extract_tool_calls_from_response
from ..errors import DeepResearchError
from ..progress import emit_progress
from .agents import ResearchAgentTeam, build_research_agent_team
from .artifacts import (
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    ResearchRunState,
    SectionResearchBrief,
    VerificationReport,
    prepare_compendium_payload,
)
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
    append_trace = state_path.exists()
    state = _load_or_create_state(
        topic=topic,
        state_path=state_path,
        output_formats=output_formats,
        cost_tracker=cost_tracker,
        config=config,
    )
    save_state(state_path, state)
    team = build_research_agent_team(config)
    trace = _contract_trace_recorder(
        _contract_trace_path(state_path),
        run_id=state.run_id,
        append=append_trace,
    )

    if state.plan is None:
        state.plan = await _run_structured_agent(
            "planning",
            team.planner,
            _planning_input(topic),
            output_type=ResearchPlan,
            config=config,
            runner=runner,
            model=config.planner_agent_model,
            cost_tracker=cost_tracker,
            state=state,
            trace=trace,
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
            model=config.research_agent_model,
            cost_tracker=cost_tracker,
            state=state,
            trace=trace,
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

    if (
        state.verification.status == "follow_up"
        and not state.follow_up_done
    ):
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

    if state.verification.status == "failed":
        save_state(state_path, state)
        raise DeepResearchError(_verification_failure_message(state))

    if state.final_payload is None:
        state.final_payload = await _run_structured_agent(
            "synthesis",
            team.synthesis,
            _synthesis_input(topic, state),
            output_type=CompendiumPayload,
            config=config,
            runner=runner,
            model=config.synthesis_agent_model,
            cost_tracker=cost_tracker,
            state=state,
            trace=trace,
        )
        _evaluate_contract_run(team, trace, state)
        state.final_payload = prepare_compendium_payload(
            state.final_payload, state.ledger
        )
        state.mark_completed("synthesis")
        save_state(state_path, state)
    else:
        prepared_payload = prepare_compendium_payload(
            state.final_payload, state.ledger
        )
        if prepared_payload != state.final_payload:
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
        payload=state.final_payload.to_payload(),
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
    trace: TraceRecorder,
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
    trace: TraceRecorder,
) -> None:
    section_ids = list(dict.fromkeys(state.verification.follow_up_section_ids))
    for section_id in section_ids:
        if not _agenda_section(state, section_id):
            continue
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
    trace: TraceRecorder,
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
        model=config.research_agent_model,
        cost_tracker=cost_tracker,
        state=state,
        trace=trace,
        metadata={"section_id": section_id, "follow_up": follow_up},
    )


async def _verify(
    state: ResearchRunState,
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    trace: TraceRecorder,
):
    return await _run_structured_agent(
        "verification",
        team.verifier,
        _verification_input(state),
        output_type=VerificationReport,
        config=config,
        runner=runner,
        model=config.verifier_agent_model,
        cost_tracker=cost_tracker,
        state=state,
        trace=trace,
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
                brief.model_dump(mode="json")
                for brief in state.section_briefs.values()
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
                brief.model_dump(mode="json")
                for brief in state.section_briefs.values()
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
    model: str,
    cost_tracker: "CostTracker | None",
    state: ResearchRunState,
    trace: TraceRecorder,
    metadata: dict[str, Any] | None = None,
) -> ArtifactT:
    agent_name = str(getattr(agent, "name", phase))
    trace.record(
        "agent.started",
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
    _record_hosted_tool_events(trace, agent_name, result)
    trace.record("agent.completed", agent=agent_name, data={"phase": phase})
    record_agent_result_cost(
        cost_tracker,
        phase=phase,
        model=model,
        result=result,
    )
    state.response_ids[phase] = list(
        dict.fromkeys(state.response_ids.get(phase, []) + result.response_ids)
    )
    artifact = _coerce_artifact(result, output_type)
    trace.record(
        "output.accepted",
        stage=phase,
        data={"agent_name": agent_name, "output_type": output_type.__name__},
    )
    trace.record(
        "stage.completed",
        stage=phase,
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
        return output
    if isinstance(output, dict):
        return output_type.model_validate(output)
    if isinstance(output, str):
        return output_type.model_validate_json(output)
    return output_type.model_validate(output)


def _record_hosted_tool_events(
    trace: TraceRecorder,
    agent_name: str,
    result: AgentRunResult,
) -> None:
    raw_result = getattr(result, "raw_result", result)
    for response in list(getattr(raw_result, "raw_responses", []) or []):
        web_search_count = extract_tool_calls_from_response(response).get(
            "web_search_call",
            0,
        )
        for _ in range(web_search_count):
            data = {"tool": "openai.web_search", "agent_name": agent_name}
            if agent_name == "SynthesisAgent":
                trace.record(
                    "hosted_tool.completed",
                    agent=agent_name,
                    tool="openai.web_search",
                )
            else:
                trace.record("hosted_tool.completed", data=data)


def _evaluate_contract_run(
    team: ResearchAgentTeam,
    trace: TraceRecorder,
    state: ResearchRunState,
) -> None:
    result = evaluate_run_spec(
        contract=team.artifacts,
        run_spec="CompendiumResearch",
        trace=trace,
        stage_outputs=_run_spec_stage_outputs(state),
        derived_values=_run_spec_derived_values(state),
        run_id=state.run_id,
    )
    if not result.passed:
        raise ValueError(_contract_failure_message(result))


def _run_spec_stage_outputs(state: ResearchRunState) -> dict[str, Any]:
    return {
        "planning": state.plan.model_dump(mode="json"),
        "research_agenda": state.agenda.model_dump(mode="json"),
        "section_research": [
            brief.model_dump(mode="json")
            for brief in state.section_briefs.values()
        ],
        "verification": [state.verification.model_dump(mode="json")],
        "synthesis": state.final_payload.model_dump(mode="json"),
    }


def _run_spec_derived_values(state: ResearchRunState) -> dict[str, list[str]]:
    return {
        "ledger_cited_ids": [
            entry.id for entry in state.ledger.entries if entry.status == "cited"
        ],
        "synthesis_citation_ids": [
            citation_id
            for section in state.final_payload.sections
            for insight in section.insights
            for citation_id in insight.citations
        ],
    }


def _contract_failure_message(result: RunSpecEvaluationResult) -> str:
    details = "; ".join(
        f"{failure.kind}: {failure.message}" for failure in result.failures
    )
    return (
        f"Contract4Agents run spec `{result.run_spec}` failed: "
        f"{details or 'unspecified failure'}"
    )


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
) -> ResearchRunState:
    if state_path.exists():
        return load_state(state_path)
    return ResearchRunState(
        topic=topic,
        title=topic,
        output_formats=list(output_formats),
        cost_report_path=str(cost_tracker.path) if cost_tracker else None,
        config_snapshot=config.model_snapshot(),
    )


def _json_prompt(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _agenda_section(state: ResearchRunState, section_id: str):
    for section in state.agenda.sections:
        if section.id == section_id:
            return section
    return None


def _verification_failure_message(state: ResearchRunState) -> str:
    issues = state.verification.issues if state.verification else []
    details = "; ".join(issue.message for issue in issues) or "unspecified"
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
) -> TraceRecorder:
    trace = TraceRecorder(path, run_id=run_id, append=append)
    if append and path.exists():
        trace.events = load_trace_jsonl(path).events
        trace._path_initialized = True
        trace._event_index = len(trace.events)
    return trace


__all__ = [
    "build_compendium_with_agents",
    "recover_compendium_from_state",
]
