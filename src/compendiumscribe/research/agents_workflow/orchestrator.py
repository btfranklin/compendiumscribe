from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
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
from ..errors import DeepResearchError, ResearchApprovalRequired
from ..progress import emit_progress
from .agents import ResearchAgentTeam, build_research_agent_team
from ...agent_contracts.generated.python import (
    CompendiumPayload,
    EvidenceRepairResult,
    ResearchAgenda,
    ResearchPlan,
    ResearchSource,
    SectionContentRevision,
    SectionResearchBrief,
    TargetedResearchResult,
    TargetedSectionRevision,
    VerificationIssue,
    VerificationReport,
)
from .artifacts import CompletedAgentStage, ResearchRunState, prepare_compendium_payload
from .contract_trace import ContractTraceRecorder
from .costing import record_agent_result_cost
from .runner import AgentRunResult, AgentRunner, OpenAIAgentRunner
from .source_ledger import build_source_ledger, mark_cited_sources, normalize_url
from .state import load_state, save_state

if TYPE_CHECKING:
    from ..costs import CostTracker
    from openai import AsyncOpenAI

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)
AGENT_MAX_TURNS = {
    "PlannerAgent": 2,
    "ResearchManagerAgent": 4,
    "SectionResearchAgent": 8,
    "EvidenceRepairAgent": 2,
    "TargetedResearchAgent": 6,
    "VerifierAgent": 2,
    "SynthesisAgent": 2,
}

AGENT_MAX_ATTEMPTS = {
    "PlannerAgent": 3,
    "ResearchManagerAgent": 2,
    "SectionResearchAgent": 2,
    "EvidenceRepairAgent": 3,
    "TargetedResearchAgent": 2,
    "VerifierAgent": 3,
    "SynthesisAgent": 3,
}


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
                allow_paid_follow_up=False,
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
    allow_paid_follow_up: bool = False,
) -> Compendium:
    state = load_state(state_path)
    config = config or ResearchConfig()
    runner = runner or OpenAIAgentRunner(openai_client=client)
    return asyncio.run(
        _build_compendium_async(
            state.topic,
            config=config,
            runner=runner,
            state_path=state_path,
            cost_tracker=cost_tracker,
            output_formats=state.output_formats,
            allow_paid_follow_up=allow_paid_follow_up,
        )
    )


async def _build_compendium_async(
    topic: str,
    *,
    config: ResearchConfig,
    runner: AgentRunner,
    state_path: Path,
    cost_tracker: "CostTracker | None",
    output_formats: list[str],
    allow_paid_follow_up: bool,
) -> Compendium:
    state_path_existed = state_path.exists()
    team = build_research_agent_team(config)
    state = _load_or_create_state(
        topic=topic,
        state_path=state_path,
        output_formats=output_formats,
        cost_tracker=cost_tracker,
        config=config,
        plan=team.materialization.plan,
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
            _validate_contract_trace(
                team.materialization.artifacts.ir,
                team.materialization.plan,
                trace.trace,
            )
        _reconcile_terminal_attempts(state, trace)
        if trace.events:
            _validate_contract_trace(
                team.materialization.artifacts.ir,
                team.materialization.plan,
                trace.trace,
            )
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
            allow_paid_follow_up=allow_paid_follow_up,
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
    allow_paid_follow_up: bool,
) -> Compendium:
    if state.plan is None:
        state.plan = await _run_structured_agent(
            "planning",
            "PlannerAgent",
            _planning_input(topic),
            output_type=ResearchPlan,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state=state,
            state_path=state_path,
            trace=trace,
            team=team,
            invocation_key="planning",
        )
        state.title = state.plan.title
        state.mark_completed("planning")
        _checkpoint_state(state_path, state, trace)

    if state.agenda is None:
        state.agenda = await _run_structured_agent(
            "research_agenda",
            "ResearchManagerAgent",
            _research_agenda_input(topic, state),
            output_type=ResearchAgenda,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state=state,
            state_path=state_path,
            trace=trace,
            team=team,
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

    if not state.verification_reports:
        initial_verification = await _verify(
            state,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state_path=state_path,
            trace=trace,
            final_verification=False,
        )
        state.verification_reports.append(initial_verification)
        state.mark_completed("verification")
        _checkpoint_state(state_path, state, trace)

    initial_verification = state.verification_reports[0]
    if initial_verification.status == "failed":
        _checkpoint_state(state_path, state, trace)
        raise DeepResearchError(
            _verification_failure_message(initial_verification, final=False)
        )

    repair_issues = _issues_with_resolution(initial_verification, "repair")
    research_issues = _issues_with_resolution(initial_verification, "research")

    if repair_issues and "evidence_repair" not in state.completed_stages:
        repair = await _run_evidence_repair(
            state,
            repair_issues,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state_path=state_path,
            trace=trace,
        )
        _apply_evidence_repair(state, repair, repair_issues)
        _rebuild_ledger(state)
        state.mark_completed("evidence_repair")
        _checkpoint_state(state_path, state, trace)

    if research_issues and "targeted_research" not in state.completed_stages:
        if not allow_paid_follow_up:
            _checkpoint_state(state_path, state, trace)
            raise ResearchApprovalRequired(
                state_path,
                tuple(issue.code for issue in research_issues),
            )
        targeted = await _run_targeted_research(
            state,
            research_issues,
            team=team,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state_path=state_path,
            trace=trace,
        )
        _apply_targeted_research(state, targeted, research_issues)
        _rebuild_ledger(state)
        state.mark_completed("targeted_research")
        _checkpoint_state(state_path, state, trace)

    if repair_issues or research_issues:
        if len(state.verification_reports) < 2:
            final_verification = await _verify(
                state,
                team=team,
                config=config,
                runner=runner,
                cost_tracker=cost_tracker,
                state_path=state_path,
                trace=trace,
                final_verification=True,
            )
            state.verification_reports.append(final_verification)
            state.mark_completed("final_verification")
            _checkpoint_state(state_path, state, trace)

    verification = state.verification_reports[-1]
    if verification.status != "accepted":
        _checkpoint_state(state_path, state, trace)
        raise DeepResearchError(
            _verification_failure_message(verification, final=True)
        )

    if state.final_payload is None:
        state.final_payload = await _run_structured_agent(
            "synthesis",
            "SynthesisAgent",
            _synthesis_input(topic, state),
            output_type=CompendiumPayload,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state=state,
            state_path=state_path,
            trace=trace,
            team=team,
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


async def _run_evidence_repair(
    state: ResearchRunState,
    issues: list[VerificationIssue],
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state_path: Path,
    trace: ContractTraceRecorder,
) -> EvidenceRepairResult:
    return await _run_structured_agent(
        "evidence_repair",
        "EvidenceRepairAgent",
        _evidence_repair_input(state, issues),
        output_type=EvidenceRepairResult,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
        state=state,
        state_path=state_path,
        trace=trace,
        team=team,
        invocation_key="evidence_repair",
        artifact_validator=lambda result: _validate_evidence_repair(
            state, result, issues
        ),
    )


async def _run_targeted_research(
    state: ResearchRunState,
    issues: list[VerificationIssue],
    *,
    team: ResearchAgentTeam,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state_path: Path,
    trace: ContractTraceRecorder,
) -> TargetedResearchResult:
    return await _run_structured_agent(
        "targeted_research",
        "TargetedResearchAgent",
        _targeted_research_input(state, issues),
        output_type=TargetedResearchResult,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
        state=state,
        state_path=state_path,
        trace=trace,
        team=team,
        invocation_key="targeted_research",
        artifact_validator=lambda result: _validate_targeted_research(
            state, result, issues
        ),
    )


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
) -> SectionResearchBrief:
    section = _agenda_section(state, section_id)
    if section is None:
        raise DeepResearchError(f"Unknown agenda section: {section_id}")
    return await _run_structured_agent(
        "section_research",
        "SectionResearchAgent",
        _section_research_input(state, section),
        output_type=SectionResearchBrief,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
        state=state,
        state_path=state_path,
        trace=trace,
        team=team,
        invocation_key=f"section_research:{section_id}",
        metadata={"section_id": section_id},
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
    final_verification: bool,
):
    return await _run_structured_agent(
        "verification",
        "VerifierAgent",
        _verification_input(state, final_verification=final_verification),
        output_type=VerificationReport,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
        state=state,
        state_path=state_path,
        trace=trace,
        team=team,
        invocation_key=(
            "final_verification" if final_verification else "verification"
        ),
        artifact_validator=lambda report: _validate_verification_report(
            state, report, final_verification=final_verification
        ),
    )


def _planning_input(topic: str) -> dict[str, Any]:
    return {"topic": topic}


def _research_agenda_input(topic: str, state: ResearchRunState) -> dict[str, Any]:
    return {
        "topic": topic,
        "plan": state.plan.model_dump(mode="json"),
    }


def _section_research_input(
    state: ResearchRunState,
    section: Any,
) -> dict[str, Any]:
    return {
        "topic": state.title or state.topic,
        "section": section.model_dump(mode="json"),
        "plan": state.plan.model_dump(mode="json"),
        "agenda": state.agenda.model_dump(mode="json"),
    }


def _evidence_repair_input(
    state: ResearchRunState,
    issues: list[VerificationIssue],
) -> dict[str, Any]:
    section_ids = _issue_section_ids(issues)
    return {
        "affected_briefs": [
            state.section_briefs[section_id].model_dump(mode="json")
            for section_id in section_ids
        ],
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }


def _targeted_research_input(
    state: ResearchRunState,
    issues: list[VerificationIssue],
) -> dict[str, Any]:
    section_ids = _issue_section_ids(issues)
    return {
        "topic": state.title or state.topic,
        "affected_briefs": [
            state.section_briefs[section_id].model_dump(mode="json")
            for section_id in section_ids
        ],
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }


def _verification_input(
    state: ResearchRunState,
    *,
    final_verification: bool,
) -> dict[str, Any]:
    return {
        "topic": state.title or state.topic,
        "plan": state.plan.model_dump(mode="json"),
        "agenda": state.agenda.model_dump(mode="json"),
        "section_briefs": [
            brief.model_dump(mode="json") for brief in state.section_briefs.values()
        ],
        "source_ledger": state.ledger.model_dump(mode="json"),
        "final_verification": final_verification,
    }


def _synthesis_input(topic: str, state: ResearchRunState) -> dict[str, Any]:
    return {
        "topic": state.title or topic,
        "plan": state.plan.model_dump(mode="json"),
        "agenda": state.agenda.model_dump(mode="json"),
        "section_briefs": [
            brief.model_dump(mode="json") for brief in state.section_briefs.values()
        ],
        "source_ledger": state.ledger.model_dump(mode="json"),
        "verification": state.verification_reports[-1].model_dump(mode="json"),
    }


def _issues_with_resolution(
    report: VerificationReport,
    resolution: str,
) -> list[VerificationIssue]:
    return [issue for issue in report.issues if issue.resolution == resolution]


def _issue_section_ids(issues: list[VerificationIssue]) -> list[str]:
    return list(dict.fromkeys(str(issue.section_id) for issue in issues))


def _validate_verification_report(
    state: ResearchRunState,
    report: VerificationReport,
    *,
    final_verification: bool,
) -> None:
    agenda_ids = {section.id for section in state.agenda.sections}
    codes = [issue.code for issue in report.issues]
    if len(codes) != len(set(codes)):
        raise ValueError("Verification issue codes must be unique.")

    for issue in report.issues:
        if issue.section_id is not None and issue.section_id not in agenda_ids:
            raise ValueError(
                f"Verification issue {issue.code} names unknown section "
                f"{issue.section_id}."
            )
        if issue.severity == "warning" and issue.resolution != "none":
            raise ValueError(
                f"Verification warning {issue.code} must use resolution none."
            )
        if issue.severity == "error" and issue.resolution == "none":
            raise ValueError(
                f"Verification error {issue.code} must use a blocking resolution."
            )
        if issue.resolution in {"repair", "research"} and not issue.section_id:
            raise ValueError(
                f"Verification issue {issue.code} must name a section."
            )
        if issue.resolution == "fatal" and issue.severity != "error":
            raise ValueError(
                f"Fatal verification issue {issue.code} must be an error."
            )

    error_resolutions = {
        issue.resolution for issue in report.issues if issue.severity == "error"
    }
    if report.status == "accepted" and error_resolutions:
        raise ValueError("An accepted verification report cannot contain errors.")
    if report.status == "follow_up":
        if not error_resolutions or not error_resolutions <= {"repair", "research"}:
            raise ValueError(
                "A follow-up verification report must contain only repair or "
                "research errors."
            )
    if report.status == "failed":
        if "fatal" not in error_resolutions or error_resolutions != {"fatal"}:
            raise ValueError(
                "A failed verification report must contain fatal errors only."
            )
    if final_verification and report.status == "follow_up":
        raise ValueError("Final verification cannot request another follow-up.")


def _validate_evidence_repair(
    state: ResearchRunState,
    result: EvidenceRepairResult,
    issues: list[VerificationIssue],
) -> None:
    expected = set(_issue_section_ids(issues))
    revisions = _revision_map(result.revisions, expected, "Evidence repair")
    for section_id, revision in revisions.items():
        allowed_urls = {
            normalize_url(source.url)
            for source in state.section_briefs[section_id].sources
        }
        cited_urls = {
            normalize_url(url)
            for finding in revision.findings
            for url in finding.source_urls
        }
        unknown_urls = sorted(cited_urls - allowed_urls)
        if unknown_urls:
            raise ValueError(
                "Evidence repair cited source URLs that were not in the prior "
                f"brief for {section_id}: {', '.join(unknown_urls)}"
            )


def _validate_targeted_research(
    state: ResearchRunState,
    result: TargetedResearchResult,
    issues: list[VerificationIssue],
) -> None:
    expected = set(_issue_section_ids(issues))
    revisions = _revision_map(result.revisions, expected, "Targeted research")
    candidate_briefs: list[SectionResearchBrief] = []
    for section_id, revision in revisions.items():
        old = state.section_briefs[section_id]
        merged_sources = _merge_sources(old.sources, revision.sources)
        allowed_urls = {normalize_url(source.url) for source in merged_sources}
        cited_urls = {
            normalize_url(url)
            for finding in revision.findings
            for url in finding.source_urls
        }
        unknown_urls = sorted(cited_urls - allowed_urls)
        if unknown_urls:
            raise ValueError(
                "Targeted research cited source URLs without source records for "
                f"{section_id}: {', '.join(unknown_urls)}"
            )
        candidate_briefs.append(
            _targeted_brief(old, revision, merged_sources=merged_sources)
        )
    build_source_ledger(candidate_briefs)


def _revision_map(
    revisions: list[SectionContentRevision] | list[TargetedSectionRevision],
    expected: set[str],
    label: str,
) -> dict[str, SectionContentRevision | TargetedSectionRevision]:
    section_ids = [revision.section_id for revision in revisions]
    if len(section_ids) != len(set(section_ids)):
        raise ValueError(f"{label} returned duplicate section revisions.")
    if set(section_ids) != expected:
        raise ValueError(
            f"{label} must return exactly these sections: "
            + ", ".join(sorted(expected))
        )
    return {revision.section_id: revision for revision in revisions}


def _apply_evidence_repair(
    state: ResearchRunState,
    result: EvidenceRepairResult,
    issues: list[VerificationIssue],
) -> None:
    revisions = _revision_map(
        result.revisions,
        set(_issue_section_ids(issues)),
        "Evidence repair",
    )
    for section_id, revision in revisions.items():
        old = state.section_briefs[section_id]
        state.section_briefs[section_id] = old.model_copy(
            update={
                "summary": revision.summary,
                "findings": revision.findings,
                "open_questions": revision.open_questions,
            }
        )


def _apply_targeted_research(
    state: ResearchRunState,
    result: TargetedResearchResult,
    issues: list[VerificationIssue],
) -> None:
    revisions = _revision_map(
        result.revisions,
        set(_issue_section_ids(issues)),
        "Targeted research",
    )
    for section_id, revision in revisions.items():
        old = state.section_briefs[section_id]
        state.section_briefs[section_id] = _targeted_brief(
            old,
            revision,
            merged_sources=_merge_sources(old.sources, revision.sources),
        )


def _targeted_brief(
    old: SectionResearchBrief,
    revision: TargetedSectionRevision,
    *,
    merged_sources: list[ResearchSource],
) -> SectionResearchBrief:
    return old.model_copy(
        update={
            "summary": revision.summary,
            "findings": revision.findings,
            "sources": merged_sources,
            "open_questions": revision.open_questions,
        }
    )


def _merge_sources(
    existing: list[ResearchSource],
    returned: list[ResearchSource],
) -> list[ResearchSource]:
    merged = list(existing)
    by_url = {normalize_url(source.url): source for source in existing}
    returned_urls: set[str] = set()
    for source in returned:
        normalized = normalize_url(source.url)
        if normalized in returned_urls:
            raise ValueError("Targeted research returned duplicate source URLs.")
        returned_urls.add(normalized)
        if normalized not in by_url:
            merged.append(source)
            by_url[normalized] = source
    return merged


async def _run_structured_agent(
    phase: str,
    agent_name: str,
    input_data: Mapping[str, object],
    *,
    output_type: type[ArtifactT],
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state: ResearchRunState,
    state_path: Path,
    trace: ContractTraceRecorder,
    team: ResearchAgentTeam,
    invocation_key: str,
    metadata: dict[str, Any] | None = None,
    artifact_validator: Callable[[ArtifactT], None] | None = None,
) -> ArtifactT:
    materialization = team.materialization
    agent = materialization.agents[agent_name]
    plan = materialization.plan
    ir = materialization.artifacts.ir
    input_payload = materialization.serialize_agent_input(
        agent_name,
        {"request": input_data},
    )
    max_turns = _agent_limit(AGENT_MAX_TURNS, agent_name, "turn")
    max_attempts = _agent_limit(AGENT_MAX_ATTEMPTS, agent_name, "attempt")
    invocation_id = f"{state.run_id}:{invocation_key}"
    while True:
        attempt = _next_attempt(trace, invocation_id)
        if attempt.number > max_attempts:
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
                f"{agent_name} failed after {max_attempts} attempts."
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
            "max_attempts": max_attempts,
        }
        emit_progress(
            config,
            phase=phase,
            status="in_progress",
            message=(
                f"Running {agent_name}, attempt {attempt.number} of "
                f"{max_attempts}."
            ),
            metadata=progress_metadata,
        )
        try:
            with trace.bind_attempt(attempt, agent_name=agent_name):
                trace.checkpoint()
                result = await runner.run(
                    agent,
                    input_payload,
                    max_turns=max_turns,
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
            terminal = attempt.number == max_attempts or any(
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
                max_attempts=max_attempts,
            )
            continue

        raw_result = getattr(result, "raw_result", result)
        response_events = trace.record_result(
            raw_result,
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
            if artifact_validator is not None:
                artifact_validator(artifact)
        except (ValidationError, ValueError):
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
            terminal = attempt.number == max_attempts
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
                max_attempts=max_attempts,
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
    max_attempts: int,
) -> None:
    emit_progress(
        config,
        phase=phase,
        status="update",
        message=(
            f"Retrying {agent_name} after attempt {attempt.number} of "
            f"{max_attempts} failed."
        ),
        metadata={
            **(metadata or {}),
            "attempt_number": attempt.number,
            "max_attempts": max_attempts,
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
    materialization = team.materialization
    ir = materialization.artifacts.ir
    plan = materialization.plan
    _validate_contract_trace(ir, plan, trace)
    control_results = assess_controls(
        ir,
        plan,
        trace,
        closure=closure,
        run_id=state.run_id,
    )
    run_spec_id = next(
        (
            item.id
            for item in ir.run_specs.values()
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
        ir,
        plan,
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

    optional_agents = {"EvidenceRepairAgent", "TargetedResearchAgent"}
    observed_agents = {stage.agent_name for stage in state.agent_stages.values()}
    failures = [
        result
        for result in control_results
        if result.status != "passed"
        and not (
            result.status == "unverified"
            and any(
                str(result.control_id).startswith(f"control:{agent_name}:")
                and agent_name not in observed_agents
                for agent_name in optional_agents
            )
        )
    ]
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


def _agenda_section(state: ResearchRunState, section_id: str):
    for section in state.agenda.sections:
        if section.id == section_id:
            return section
    return None


def _state_requires_trace(state: ResearchRunState) -> bool:
    return bool(
        state.completed_stages
        or state.response_ids
        or state.attempt_counts
        or state.agent_stages
        or state.plan is not None
        or state.agenda is not None
        or state.section_briefs
        or state.verification_reports
        or state.final_payload is not None
        or state.run_spec_result is not None
    )


def _verification_failure_message(
    report: VerificationReport,
    *,
    final: bool,
) -> str:
    details = "; ".join(
        f"{issue.code}: {issue.message}" for issue in report.issues
    ) or "unspecified"
    if final:
        return f"Final research verification failed: {details}"
    return f"Research verification failed: {details}"


def _agent_limit(limits: Mapping[str, int], agent_name: str, label: str) -> int:
    try:
        return limits[agent_name]
    except KeyError as exc:
        raise DeepResearchError(
            f"No {label} limit is configured for {agent_name}."
        ) from exc


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
            ir=team.materialization.artifacts.ir,
            plan=team.materialization.plan,
            append=append,
        )
    except (OSError, ValueError) as exc:
        raise DeepResearchError(
            f"Cannot recover Contract4Agents trace evidence from {path}: {exc}"
        ) from exc


__all__ = [
    "AGENT_MAX_ATTEMPTS",
    "AGENT_MAX_TURNS",
    "build_compendium_with_agents",
    "recover_compendium_from_state",
]
