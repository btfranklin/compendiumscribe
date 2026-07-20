from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeVar

from contract4agents.assurance import (
    RunSpecEvidence,
    RunSpecSelection,
    RunSpecStageObservation,
    assess_controls,
    assess_run_spec,
)
from contract4agents.ir import CanonicalIR, semantic_id
from contract4agents.planning import MaterializationPlan
from contract4agents.tracing import (
    NormalizedTrace,
    TraceAttempt,
    TraceClosureEvidence,
    TraceConformanceError,
    TraceEvent,
    validate_trace_conformance,
)
from pydantic import BaseModel, ValidationError

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
from .artifacts import CompletedAgentStage, ResearchRunState, prepare_compendium_payload
from .contract_trace import ContractTraceRecorder
from .costing import record_agent_result_cost
from .runner import AgentRunResult, AgentRunner, OpenAIAgentRunner
from .source_ledger import build_source_ledger, mark_cited_sources
from .state import load_state, save_state

if TYPE_CHECKING:
    from ..costs import CostTracker
    from openai import AsyncOpenAI

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)
MAX_AGENT_ATTEMPTS = 5


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
    closure_path = _contract_trace_closure_path(state_path)
    trace_required = _state_requires_trace(state)
    if trace_required and not trace_path.exists():
        raise DeepResearchError(
            f"Cannot recover progressed research state without trace evidence: "
            f"{trace_path}"
        )
    if trace_required and not closure_path.exists():
        raise DeepResearchError(
            "Cannot recover progressed research state without trace-closure "
            f"evidence: {closure_path}"
        )
    save_state(state_path, state)
    trace = _contract_trace_recorder(
        trace_path,
        closure_path,
        run_id=state.run_id,
        append=state_path_existed and trace_path.exists(),
        team=team,
    )
    try:
        if trace_required and not trace.events:
            raise DeepResearchError(
                "Cannot recover progressed research state from an empty trace: "
                f"{trace_path}"
            )
        if trace.events:
            _validate_contract_trace(team.ir, team.plan, trace.trace)
        _reconcile_terminal_attempts(state, trace)
        if trace.events:
            _validate_contract_trace(team.ir, team.plan, trace.trace)
            trace.checkpoint()
        return await _continue_research_workflow(
            topic,
            config=config,
            runner=runner,
            state_path=state_path,
            cost_tracker=cost_tracker,
            team=team,
            state=state,
            trace=trace,
        )
    finally:
        trace.close()


async def _continue_research_workflow(
    topic: str,
    *,
    config: ResearchConfig,
    runner: AgentRunner,
    state_path: Path,
    cost_tracker: "CostTracker | None",
    team: ResearchAgentTeam,
    state: ResearchRunState,
    trace: ContractTraceRecorder,
) -> Compendium:
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
            state_path=state_path,
            trace=trace,
            plan=team.plan,
            ir=team.ir,
            invocation_key="planning",
        )
        state.title = state.plan.title
        state.mark_completed("planning")
        _checkpoint_state(state_path, state, trace)

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
            state_path=state_path,
            trace=trace,
            plan=team.plan,
            ir=team.ir,
            invocation_key="research_agenda",
        )
        state.mark_completed("research_agenda")
        _checkpoint_state(state_path, state, trace)

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
    _checkpoint_state(state_path, state, trace)

    if state.verification is None:
        state.verification = await _verify(
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state_path=state_path,
            trace=trace,
        )
        state.mark_completed(
            "verification_follow_up" if state.follow_up_done else "verification"
        )
        _checkpoint_state(state_path, state, trace)

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
        state.verification = None
        _checkpoint_state(state_path, state, trace)
        state.verification = await _verify(
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state_path=state_path,
            trace=trace,
        )
        state.mark_completed("verification_follow_up")
        _checkpoint_state(state_path, state, trace)

    if state.verification.status != "accepted":
        _checkpoint_state(state_path, state, trace)
        raise DeepResearchError(_verification_failure_message(state))

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
            state_path=state_path,
            trace=trace,
            plan=team.plan,
            ir=team.ir,
            invocation_key="synthesis",
        )
        state.mark_completed("synthesis")
        _checkpoint_state(state_path, state, trace)

    snapshot = trace.close()
    try:
        _evaluate_contract_run(team, snapshot.trace, snapshot.closure, state)
    except DeepResearchError:
        save_state(state_path, state)
        raise
    prepared_payload = prepare_compendium_payload(state.final_payload, state.ledger)
    if prepared_payload != state.final_payload:
        state.final_payload = prepared_payload
    _checkpoint_state(state_path, state, trace)

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
            state_path=state_path,
            trace=trace,
        )
        state.mark_completed(f"section_research:{section.id}")
        _checkpoint_state(state_path, state, trace)


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
        stage = f"section_follow_up:{section_id}"
        if stage in state.completed_stages:
            continue
        state.section_briefs[section_id] = await _run_section_agent(
            section_id,
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state_path=state_path,
            trace=trace,
            follow_up=True,
        )
        state.mark_completed(stage)
        _checkpoint_state(state_path, state, trace)


async def _run_section_agent(
    section_id: str,
    state: ResearchRunState,
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state_path: Path,
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
        state_path=state_path,
        trace=trace,
        plan=team.plan,
        ir=team.ir,
        invocation_key=(
            f"section_follow_up:{section_id}"
            if follow_up
            else f"section_research:{section_id}"
        ),
        metadata={"section_id": section_id, "follow_up": follow_up},
    )


async def _verify(
    state: ResearchRunState,
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state_path: Path,
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
        state_path=state_path,
        trace=trace,
        plan=team.plan,
        ir=team.ir,
        invocation_key=(
            "verification_follow_up" if state.follow_up_done else "verification"
        ),
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
    state_path: Path,
    trace: ContractTraceRecorder,
    plan: MaterializationPlan,
    ir: CanonicalIR,
    invocation_key: str,
    metadata: dict[str, Any] | None = None,
) -> ArtifactT:
    agent_name = str(getattr(agent, "name", phase))
    invocation_id = f"{state.run_id}:{invocation_key}"
    while True:
        attempt = _next_attempt(trace, invocation_id)
        if attempt.number > MAX_AGENT_ATTEMPTS:
            exhausted = _latest_attempt(trace, invocation_id)
            if exhausted is not None:
                _record_terminal_failure(
                    trace,
                    agent_name=agent_name,
                    attempt=exhausted,
                )
            _checkpoint_attempt_evidence(
                state_path,
                state,
                trace,
                ir=ir,
                plan=plan,
            )
            raise DeepResearchError(
                f"{agent_name} failed after {MAX_AGENT_ATTEMPTS} attempts."
            )

        trace.record(
            "agent.started",
            agent_name=agent_name,
            data={
                "agent_name": agent_name,
                "invocation_key": invocation_key,
                "phase": phase,
            },
            attempt=attempt,
        )
        state.attempt_counts[invocation_id] = attempt.number
        save_state(state_path, state)
        _validate_contract_trace(ir, plan, trace.trace)
        progress_metadata = {
            **(metadata or {}),
            "attempt_number": attempt.number,
            "max_attempts": MAX_AGENT_ATTEMPTS,
        }
        emit_progress(
            config,
            phase=phase,
            status="in_progress",
            message=(
                f"Running {agent_name}, attempt {attempt.number} of "
                f"{MAX_AGENT_ATTEMPTS}."
            ),
            metadata=progress_metadata,
        )
        try:
            with trace.bind_attempt(attempt, agent_name=agent_name):
                trace.checkpoint()
                result = await runner.run(
                    agent,
                    input_payload,
                    max_turns=config.max_agent_turns,
                )
        except Exception as exc:
            exception_events = trace.normalize_exception_responses(
                exc,
                agent_name=agent_name,
                attempt=attempt,
            )
            trace.record(
                "agent.failed",
                agent_name=agent_name,
                data={"phase": phase, "reason": type(exc).__name__},
                attempt=attempt,
            )
            terminal = attempt.number == MAX_AGENT_ATTEMPTS or any(
                event.event_type == "capability.undeclared"
                for event in exception_events
            )
            if terminal:
                _record_terminal_failure(
                    trace,
                    agent_name=agent_name,
                    attempt=attempt,
                )
            _checkpoint_attempt_evidence(
                state_path,
                state,
                trace,
                ir=ir,
                plan=plan,
            )
            if terminal:
                raise
            _emit_retry_progress(
                config,
                phase=phase,
                agent_name=agent_name,
                attempt=attempt,
                metadata=metadata,
            )
            continue

        raw_result = getattr(result, "raw_result", result)
        response_events = trace.normalize_response_events(
            list(getattr(raw_result, "raw_responses", []) or []),
            agent_name=agent_name,
            attempt=attempt,
        )
        if any(
            event.event_type == "capability.undeclared"
            for event in response_events
        ):
            trace.record(
                "agent.failed",
                agent_name=agent_name,
                data={"phase": phase, "reason": "capability_undeclared"},
                response_ids=result.response_ids,
                attempt=attempt,
            )
            _record_terminal_failure(
                trace,
                agent_name=agent_name,
                attempt=attempt,
            )
            _checkpoint_attempt_evidence(
                state_path,
                state,
                trace,
                ir=ir,
                plan=plan,
            )
            raise DeepResearchError(
                f"{agent_name} emitted undeclared capability evidence."
            )
        _validate_contract_trace(ir, plan, trace.trace)
        trace.record(
            "agent.completed",
            agent_name=agent_name,
            data={"phase": phase},
            response_ids=result.response_ids,
            attempt=attempt,
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
        try:
            artifact = _coerce_artifact(result, output_type)
        except ValidationError:
            trace.record_output_schema_failure(
                agent_name=agent_name,
                attempt=attempt,
                evidence_refs=result.response_ids,
            )
            trace.record(
                "agent.failed",
                agent_name=agent_name,
                data={"phase": phase, "reason": "output_schema"},
                response_ids=result.response_ids,
                attempt=attempt,
            )
            terminal = attempt.number == MAX_AGENT_ATTEMPTS
            if terminal:
                _record_terminal_failure(
                    trace,
                    agent_name=agent_name,
                    attempt=attempt,
                )
            _checkpoint_attempt_evidence(
                state_path,
                state,
                trace,
                ir=ir,
                plan=plan,
            )
            if terminal:
                raise
            _emit_retry_progress(
                config,
                phase=phase,
                agent_name=agent_name,
                attempt=attempt,
                metadata=metadata,
            )
            continue
        trace.record(
            "output.accepted",
            agent_name=agent_name,
            control_ids=(semantic_id("control", agent_name, "output_conformance"),),
            data={"agent_name": agent_name, "output_type": output_type.__name__},
            response_ids=result.response_ids,
            attempt=attempt,
        )
        trace.record(
            "stage.completed",
            agent_name=agent_name,
            data={
                "agent_name": agent_name,
                "invocation_key": invocation_key,
                "metadata": metadata or {},
                "output_type": output_type.__name__,
                "stage": phase,
            },
            response_ids=result.response_ids,
            attempt=attempt,
        )
        state.agent_stages[invocation_id] = CompletedAgentStage(
            stage=phase,
            agent_name=agent_name,
            output_type=output_type.__name__,
            output=artifact.model_dump(mode="json"),
            invocation_id=attempt.invocation_id,
            attempt_id=attempt.attempt_id,
            attempt_number=attempt.number,
            retry_of=attempt.retry_of,
        )
        emit_progress(
            config,
            phase=phase,
            status="completed",
            message=f"Accepted {agent_name} output.",
            metadata=progress_metadata,
        )
        return artifact


def _emit_retry_progress(
    config: ResearchConfig,
    *,
    phase: str,
    agent_name: str,
    attempt: TraceAttempt,
    metadata: dict[str, Any] | None,
) -> None:
    emit_progress(
        config,
        phase=phase,
        status="update",
        message=(
            f"Retrying {agent_name} after attempt {attempt.number} of "
            f"{MAX_AGENT_ATTEMPTS} failed."
        ),
        metadata={
            **(metadata or {}),
            "attempt_number": attempt.number,
            "max_attempts": MAX_AGENT_ATTEMPTS,
        },
    )


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


def _evaluate_contract_run(
    team: ResearchAgentTeam,
    trace: NormalizedTrace,
    closure: TraceClosureEvidence,
    state: ResearchRunState,
) -> None:
    _validate_contract_trace(team.ir, team.plan, trace)
    control_results = assess_controls(
        team.ir,
        team.plan,
        trace,
        closure=closure,
        run_id=state.run_id,
    )
    run_spec_id = next(
        (
            item.id
            for item in team.ir.run_specs.values()
            if item.name == "CompendiumResearch"
        ),
        None,
    )
    if run_spec_id is None:
        raise DeepResearchError(
            "Contract4Agents run specification CompendiumResearch is missing."
        )
    run_spec_evidence = _run_spec_evidence(state, trace)
    run_spec_result = assess_run_spec(
        team.ir,
        team.plan,
        trace,
        run_spec_id,
        run_spec_evidence,
        closure=closure,
        run_id=state.run_id,
    )
    selection_ref = f"research-state:{state.run_id}:agent-stages"
    selection = RunSpecSelection(
        run_id=state.run_id,
        run_spec_id=str(run_spec_id),
        reason="The host selected CompendiumResearch for this research trace.",
        evidence_refs=(selection_ref,),
    )
    state.run_spec_selection = selection.to_dict()
    state.run_spec_result = run_spec_result.to_dict()

    failures = [result for result in control_results if result.status != "passed"]
    if run_spec_result.status != "passed":
        failures.append(run_spec_result)
    if failures:
        details = "; ".join(_assurance_failure_detail(result) for result in failures)
        raise DeepResearchError(f"Contract4Agents assurance failed: {details}")


def _run_spec_evidence(
    state: ResearchRunState,
    trace: NormalizedTrace,
) -> RunSpecEvidence:
    observations: list[RunSpecStageObservation] = []
    missing_refs: list[str] = []
    for completed in state.agent_stages.values():
        stage_event = _stage_event_for_attempt(trace, completed.attempt_id)
        if stage_event is None:
            missing_refs.append(completed.invocation_id)
            continue
        observations.append(
            RunSpecStageObservation(
                observation_id=f"host-stage:{completed.attempt_id}",
                stage=completed.stage,
                agent_id=semantic_id("agent", completed.agent_name),
                output=completed.output,
                evidence_event_ids=(stage_event.event_id,),
                evidence_refs=(
                    f"research-state:{state.run_id}:agent-stage:{completed.invocation_id}",
                ),
            )
        )

    evidence_ref = f"research-state:{state.run_id}:agent-stages"
    if missing_refs:
        return RunSpecEvidence(
            status="unverified",
            reason=(
                "Host stage records lack matching semantic trace evidence: "
                + ", ".join(missing_refs)
            ),
            stage_observations=tuple(observations),
            evidence_refs=(evidence_ref,),
        )
    return RunSpecEvidence(
        status="complete",
        reason="The host stage ledger contains all accepted workflow outputs.",
        stage_observations=tuple(observations),
        evidence_refs=(evidence_ref,),
    )


def _assurance_failure_detail(result: Any) -> str:
    result_id = getattr(result, "control_id", None) or getattr(
        result, "run_spec_id", "unknown"
    )
    return f"{result_id}: {result.status}: {result.reason}"


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


def _checkpoint_state(
    state_path: Path,
    state: ResearchRunState,
    trace: ContractTraceRecorder,
) -> None:
    save_state(state_path, state)
    _reconcile_terminal_attempts(state, trace)
    _validate_contract_trace(trace.ir, trace.plan, trace.trace)
    trace.checkpoint()


def _checkpoint_attempt_evidence(
    state_path: Path,
    state: ResearchRunState,
    trace: ContractTraceRecorder,
    *,
    ir: CanonicalIR,
    plan: MaterializationPlan,
) -> None:
    save_state(state_path, state)
    _validate_contract_trace(ir, plan, trace.trace)
    trace.checkpoint()


def _reconcile_terminal_attempts(
    state: ResearchRunState,
    trace: ContractTraceRecorder,
) -> None:
    selections: dict[str, tuple[str, str]] = {}
    for event in trace.events:
        if event.event_type != "attempt.selected":
            continue
        attempt_data = event.data.get("attempt")
        if not isinstance(attempt_data, Mapping):
            continue
        invocation_id = attempt_data.get("invocation_id")
        attempt_id = attempt_data.get("attempt_id")
        outcome = event.data.get("outcome")
        if all(isinstance(item, str) for item in (invocation_id, attempt_id, outcome)):
            selections[invocation_id] = (attempt_id, outcome)

    for completed in state.agent_stages.values():
        selected = selections.get(completed.invocation_id)
        if selected is not None:
            if selected != (completed.attempt_id, "succeeded"):
                raise DeepResearchError(
                    "Contract4Agents terminal attempt selection does not match "
                    f"the host stage ledger for {completed.invocation_id}."
                )
            continue
        stage_event = _stage_event_for_attempt(trace.trace, completed.attempt_id)
        if stage_event is None:
            raise DeepResearchError(
                "Cannot select a successful Contract4Agents attempt without "
                f"semantic stage evidence for {completed.invocation_id}."
            )
        trace.record_terminal_attempt(
            agent_name=completed.agent_name,
            attempt=completed.attempt,
            outcome="succeeded",
            evidence_refs=(f"trace-event:{stage_event.event_id}",),
        )


def _next_attempt(
    trace: ContractTraceRecorder,
    invocation_id: str,
) -> TraceAttempt:
    attempts = _observed_attempts(trace, invocation_id)
    number = max(attempts, default=0) + 1
    previous = attempts.get(number - 1)
    attempt_id = f"{invocation_id}:attempt:{number}"
    return TraceAttempt(
        invocation_id=invocation_id,
        attempt_id=attempt_id,
        number=number,
        retry_of=previous.attempt_id if previous is not None else None,
    )


def _latest_attempt(
    trace: ContractTraceRecorder,
    invocation_id: str,
) -> TraceAttempt | None:
    attempts = _observed_attempts(trace, invocation_id)
    return attempts[max(attempts)] if attempts else None


def _observed_attempts(
    trace: ContractTraceRecorder,
    invocation_id: str,
) -> dict[int, TraceAttempt]:
    attempts: dict[int, TraceAttempt] = {}
    for event in trace.events:
        attempt_data = event.data.get("attempt")
        if not isinstance(attempt_data, Mapping):
            continue
        try:
            observed = TraceAttempt.from_dict(attempt_data)
        except (TypeError, ValueError):
            continue
        if observed.invocation_id == invocation_id:
            attempts[observed.number] = observed
    return attempts


def _record_terminal_failure(
    trace: ContractTraceRecorder,
    *,
    agent_name: str,
    attempt: TraceAttempt,
) -> None:
    for event in trace.events:
        if event.event_type != "attempt.selected":
            continue
        attempt_data = event.data.get("attempt")
        if not isinstance(attempt_data, Mapping):
            continue
        if attempt_data.get("invocation_id") != attempt.invocation_id:
            continue
        if (
            attempt_data.get("attempt_id") == attempt.attempt_id
            and event.data.get("outcome") == "failed"
        ):
            return
        raise DeepResearchError(
            "Contract4Agents terminal attempt selection conflicts with "
            f"the failed invocation {attempt.invocation_id}."
        )

    evidence_refs = tuple(
        f"trace-event:{event.event_id}"
        for event in trace.events
        if _event_attempt_id(event) == attempt.attempt_id
        and event.event_type
        in {"agent.failed", "capability.undeclared", "output.schema_failed"}
    )
    trace.record_terminal_attempt(
        agent_name=agent_name,
        attempt=attempt,
        outcome="failed",
        evidence_refs=evidence_refs,
    )


def _event_attempt_id(event: TraceEvent) -> str | None:
    attempt_data = event.data.get("attempt")
    if not isinstance(attempt_data, Mapping):
        return None
    attempt_id = attempt_data.get("attempt_id")
    return attempt_id if isinstance(attempt_id, str) else None


def _stage_event_for_attempt(
    trace: NormalizedTrace,
    attempt_id: str,
) -> TraceEvent | None:
    matches: list[TraceEvent] = []
    for event in trace.events:
        if event.event_type != "stage.completed":
            continue
        attempt_data = event.data.get("attempt")
        if (
            isinstance(attempt_data, Mapping)
            and attempt_data.get("attempt_id") == attempt_id
        ):
            matches.append(event)
    return matches[0] if len(matches) == 1 else None


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
        or state.attempt_counts
        or state.agent_stages
        or state.plan is not None
        or state.agenda is not None
        or state.section_briefs
        or state.verification is not None
        or state.final_payload is not None
        or state.run_spec_result is not None
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


def _contract_trace_closure_path(state_path: Path) -> Path:
    return state_path.with_suffix(".trace-closure.json")


def _contract_trace_recorder(
    path: Path,
    closure_path: Path,
    *,
    run_id: str,
    append: bool,
    team: ResearchAgentTeam,
) -> ContractTraceRecorder:
    try:
        return ContractTraceRecorder(
            path,
            closure_path,
            run_id=run_id,
            ir=team.ir,
            plan=team.plan,
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
