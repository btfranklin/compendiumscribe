from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from contract4agents.tracing import (
    NormalizedTrace,
    TraceClosureManifest,
    TraceFrontier,
    load_trace_jsonl,
    write_trace_jsonl,
)
from pydantic import ValidationError
from compendiumscribe.agent_contracts.generated.python import (
    CompendiumPayload,
    EvidenceRepairResult,
    ResearchAgenda,
    ResearchPlan,
    ResearchSection,
    SectionResearchBrief,
    TargetedResearchResult,
    VerificationIssue,
    VerificationReport,
)
from compendiumscribe.research.agents_workflow import (
    AgentRunResult,
    OpenAIAgentRunner,
    ResearchRunState,
    load_state,
    save_state,
)
from compendiumscribe.research.agents_workflow.agents import build_research_agent_team
from compendiumscribe.research.agents_workflow.orchestrator import (
    _contract_trace_closure_path,
    _contract_trace_path,
    _evaluate_contract_run,
)
from compendiumscribe.research.config import ResearchConfig
from compendiumscribe.research.costs import CostPricing, CostTracker
from compendiumscribe.research.errors import (
    DeepResearchError,
    MissingConfigurationError,
    ResearchApprovalRequired,
)
from compendiumscribe.research.orchestrator import (
    build_compendium,
    recover_compendium,
)


class StubAgentRunner:
    def __init__(
        self,
        *,
        verification_reports: list[VerificationReport] | None = None,
        final_payload: CompendiumPayload | None = None,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self.turn_limits: list[tuple[str, int]] = []
        self.verification_reports = (
            [accepted_report()]
            if verification_reports is None
            else list(verification_reports)
        )
        self.final_payload = final_payload or sample_payload()

    async def run(
        self,
        agent: Any,
        input_payload: str,
        *,
        max_turns: int,
    ) -> AgentRunResult:
        name = agent.name
        self.calls.append((name, input_payload))
        self.turn_limits.append((name, max_turns))
        index = len(self.calls)
        response = SimpleNamespace(
            response_id=f"resp_{index}",
            model="gpt-provider-snapshot",
            usage={
                "input_tokens": 100,
                "input_tokens_details": {"cached_tokens": 10},
                "output_tokens": 40,
                "output_tokens_details": {"reasoning_tokens": 5},
            },
            output=(
                [{"type": "web_search_call"}]
                if name
                in {
                    "ResearchManagerAgent",
                    "SectionResearchAgent",
                    "TargetedResearchAgent",
                }
                else []
            ),
        )
        output = self._output_for(name, input_payload)
        return AgentRunResult(
            final_output=output,
            raw_result=SimpleNamespace(
                raw_responses=[response],
                context_wrapper=SimpleNamespace(
                    usage=SimpleNamespace(
                        requests=1,
                        input_tokens=100,
                        input_tokens_details=SimpleNamespace(cached_tokens=10),
                        output_tokens=40,
                        output_tokens_details=SimpleNamespace(reasoning_tokens=5),
                        total_tokens=140,
                    )
                ),
            ),
        )

    def _output_for(self, name: str, input_payload: str) -> Any:
        if name == "PlannerAgent":
            return sample_plan()
        if name == "ResearchManagerAgent":
            return sample_agenda()
        if name == "SectionResearchAgent":
            payload = json.loads(input_payload)["request"]
            return sample_brief(payload["section"]["id"])
        if name == "EvidenceRepairAgent":
            payload = json.loads(input_payload)["request"]
            return EvidenceRepairResult(
                revisions=[
                    {
                        "section_id": task["brief"]["section_id"],
                        "summary": f"Repaired {task['brief']['summary']}",
                        "findings": task["brief"]["findings"],
                        "open_questions": task["brief"]["open_questions"],
                    }
                    for task in payload["sections"]
                ]
            )
        if name == "TargetedResearchAgent":
            payload = json.loads(input_payload)["request"]
            return TargetedResearchResult(
                revisions=[
                    {
                        "section_id": task["brief"]["section_id"],
                        "summary": f"Researched {task['brief']['summary']}",
                        "findings": task["brief"]["findings"],
                        "sources": task["brief"]["sources"],
                        "open_questions": task["brief"]["open_questions"],
                    }
                    for task in payload["sections"]
                ]
            )
        if name == "VerifierAgent":
            return self.verification_reports.pop(0)
        if name == "SynthesisAgent":
            return self.final_payload
        raise AssertionError(f"Unexpected agent: {name}")


class WorkflowInterrupted(BaseException):
    """Simulate process interruption outside the retryable exception policy."""


def _load_trace_closure(state_path: Path):
    manifest = TraceClosureManifest.load(_contract_trace_closure_path(state_path))
    assert len(manifest.closures) == 1
    return manifest.closures[0]


def sample_plan() -> ResearchPlan:
    return ResearchPlan(
        title="Quantum Computing Compendium",
        primary_objective="Explain the field with sources.",
        audience="Strategic teams",
        key_sections=[
            ResearchSection(
                id="foundations",
                title="Foundations",
                focus="Core technology and milestones.",
                guiding_questions=["What changed recently?"],
            ),
            ResearchSection(
                id="applications",
                title="Applications",
                focus="Commercial deployments.",
                guiding_questions=["Where is it used?"],
            ),
            ResearchSection(
                id="risks",
                title="Risks",
                focus="Technical and operational limits.",
                guiding_questions=["What limits adoption?"],
            ),
        ],
        research_questions=["What evidence supports adoption?"],
        methodology_preferences=[],
        topic_flags=[],
    )


def sample_agenda() -> ResearchAgenda:
    return ResearchAgenda(
        sections=sample_plan().key_sections,
        source_strategy=["Use primary sources first."],
        verification_focus=["Check source coverage."],
    )


def sample_brief(section_id: str) -> SectionResearchBrief:
    return SectionResearchBrief(
        section_id=section_id,
        title=section_id.title(),
        summary=f"Summary for {section_id}.",
        key_terms=[],
        guiding_questions=[],
        findings=[
            {
                "title": "Roadmaps are more concrete",
                "evidence": "Vendors publish target milestones.",
                "implications": None,
                "source_urls": ["https://example.com/source"],
            }
        ],
        sources=[
            {
                "title": "Source",
                "url": "https://example.com/source?utm=tracking",
                "publisher": "Example",
                "published_at": None,
                "summary": None,
                "credibility_notes": None,
                "status": "consulted",
            }
        ],
        open_questions=[],
    )


def sample_payload() -> CompendiumPayload:
    return CompendiumPayload(
        topic_overview="Quantum computing is moving into pilots.",
        methodology=["Reviewed primary sources."],
        sections=[
            {
                "id": "foundations",
                "title": "Foundations",
                "summary": "Technology summary.",
                "key_terms": [],
                "guiding_questions": [],
                "insights": [
                    {
                        "title": "Roadmaps are concrete",
                        "evidence": "Vendors publish milestones.",
                        "implications": None,
                        "citations": ["C01"],
                    }
                ],
            }
        ],
        citations=[
            {
                "id": "C01",
                "title": "Source",
                "url": "https://example.com/source",
                "publisher": "Example",
                "published_at": None,
                "summary": None,
            }
        ],
        open_questions=[],
    )


def accepted_report() -> VerificationReport:
    return VerificationReport(
        status="accepted",
        issues=[],
        notes=None,
    )


def repair_report(
    *section_ids: str,
    message: str = "Needs repair.",
) -> VerificationReport:
    return VerificationReport(
        status="follow_up",
        issues=[
            VerificationIssue(
                section_id=section_id,
                code=f"repair-{index}",
                message=message,
                severity="error",
                resolution="repair",
                required_change="Correct the unsupported claim.",
            )
            for index, section_id in enumerate(section_ids, start=1)
        ],
        notes=None,
    )


def research_report(*section_ids: str) -> VerificationReport:
    return VerificationReport(
        status="follow_up",
        issues=[
            VerificationIssue(
                section_id=section_id,
                code=f"research-{index}",
                message="Needs new evidence.",
                severity="error",
                resolution="research",
                required_change="Find one primary source.",
            )
            for index, section_id in enumerate(section_ids, start=1)
        ],
        notes=None,
    )


def fatal_report(message: str = "Source coverage failed.") -> VerificationReport:
    return VerificationReport(
        status="failed",
        issues=[
            VerificationIssue(
                section_id=None,
                code="fatal-source-coverage",
                message=message,
                severity="error",
                resolution="fatal",
                required_change="Stop publication.",
            )
        ],
        notes=None,
    )


def test_build_compendium_with_stub_runner(tmp_path: Path) -> None:
    runner = StubAgentRunner()
    state_path = tmp_path / "report.research.json"

    compendium = build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=runner,
        state_path=state_path,
        output_formats=["okf", "xml"],
    )

    assert compendium.topic == "Quantum Computing Compendium"
    assert compendium.sections[0].insights[0].citation_refs == ["C01"]
    assert state_path.exists()
    state = load_state(state_path)
    assert state.plan is not None
    assert state.agenda is not None
    assert set(state.section_briefs) == {
        "foundations",
        "applications",
        "risks",
    }
    assert state.ledger.entries[0].id == "C01"
    assert state.final_payload is not None
    assert state.config_snapshot["contract4agents_profile"] == "production"
    assert state.config_snapshot["contract_digest"].startswith("sha256:")
    assert state.config_snapshot["plan_digest"].startswith("sha256:")
    assert set(state.config_snapshot["resolved_models"].values()) == {
        "gpt-5.6-sol",
        "gpt-5.6-terra",
    }
    assert state.run_spec_selection is not None
    assert state.run_spec_selection["run_spec_id"] == ("run_spec:CompendiumResearch")
    assert state.run_spec_selection["evidence_refs"]
    assert state.run_spec_result is not None
    assert state.run_spec_result["status"] == "passed"
    assert len(state.agent_stages) == 7
    trace_path = _contract_trace_path(state_path)
    assert trace_path.exists()
    loaded_trace = load_trace_jsonl(trace_path)
    closure = _load_trace_closure(state_path)
    _evaluate_contract_run(
        build_research_agent_team(ResearchConfig()),
        loaded_trace,
        closure,
        state,
    )
    outcomes = [
        event.data["evidence"]
        for event in loaded_trace.events
        if event.event_type == "provider.outcome.reported"
    ]
    usage = [
        event.data["evidence"]
        for event in loaded_trace.events
        if event.event_type == "provider.usage.reported"
    ]
    assert len(outcomes) == 7
    assert {item["outcome"] for item in outcomes} == {"succeeded"}
    assert len(usage) == 7
    assert {item["coverage"] for item in usage} == {"complete"}
    assert {item["total_tokens"] for item in usage} == {140}
    assert {item.outcome_status for item in closure.attempts} == {"complete"}
    assert {item.usage_status for item in closure.attempts} == {"complete"}
    observed_grants = {
        (
            str(event.semantic.agent_id),
            str(event.semantic.capability_id),
            str(event.semantic.grant_id),
        )
        for event in loaded_trace.events
        if event.event_type == "tool.completed"
    }
    assert observed_grants == {
        (
            "agent:ResearchManagerAgent",
            "tool:research.web_search",
            "grant:ResearchManagerAgent:research.web_search",
        ),
        (
            "agent:SectionResearchAgent",
            "tool:research.web_search",
            "grant:SectionResearchAgent:research.web_search",
        ),
    }
    assert {
        event.data.get("provider_model")
        for event in loaded_trace.events
        if event.event_type == "tool.completed"
    } == {"gpt-provider-snapshot"}
    assert [name for name, _ in runner.calls] == [
        "PlannerAgent",
        "ResearchManagerAgent",
        "SectionResearchAgent",
        "SectionResearchAgent",
        "SectionResearchAgent",
        "VerifierAgent",
        "SynthesisAgent",
    ]
    serialized_inputs = [json.loads(payload) for _, payload in runner.calls]
    assert all(set(payload) == {"request"} for payload in serialized_inputs)
    assert serialized_inputs[0] == {"request": {"topic": "Quantum Computing"}}
    assert runner.turn_limits == [
        ("PlannerAgent", 2),
        ("ResearchManagerAgent", 4),
        ("SectionResearchAgent", 8),
        ("SectionResearchAgent", 8),
        ("SectionResearchAgent", 8),
        ("VerifierAgent", 2),
        ("SynthesisAgent", 2),
    ]


def test_build_compendium_requires_profile_selection_before_workflow_setup(
    tmp_path: Path,
) -> None:
    runner = StubAgentRunner()
    state_path = tmp_path / "report.research.json"

    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(MissingConfigurationError) as exc_info:
            build_compendium(
                "Quantum Computing",
                runner=runner,
                state_path=state_path,
            )

    message = str(exc_info.value)
    assert "CONTRACT4AGENTS_PROFILE" in message
    assert runner.calls == []
    assert not state_path.exists()


def test_build_compendium_rejects_unknown_profile_as_configuration(
    tmp_path: Path,
) -> None:
    runner = StubAgentRunner()
    state_path = tmp_path / "report.research.json"

    with pytest.raises(
        MissingConfigurationError,
        match="Unknown Contract4Agents OpenAI profile: missing",
    ):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(contract4agents_profile="missing"),
            runner=runner,
            state_path=state_path,
        )

    assert runner.calls == []
    assert not state_path.exists()


def test_no_search_repair_changes_only_affected_content(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    runner = StubAgentRunner(
        verification_reports=[
            repair_report("applications"),
            accepted_report(),
        ]
    )

    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=runner,
        state_path=state_path,
    )

    names = [name for name, _ in runner.calls]
    assert names.count("SectionResearchAgent") == 3
    assert names.count("EvidenceRepairAgent") == 1
    assert names.count("VerifierAgent") == 2
    assert "TargetedResearchAgent" not in names
    repair_payload = next(
        json.loads(payload)["request"]
        for name, payload in runner.calls
        if name == "EvidenceRepairAgent"
    )
    assert repair_payload["topic"] == "Quantum Computing Compendium"
    assert repair_payload["plan"]["primary_objective"] == (
        "Explain the field with sources."
    )
    assert len(repair_payload["agenda"]["sections"]) == 3
    assert repair_payload["sections"][0]["brief"]["section_id"] == "applications"
    assert repair_payload["sections"][0]["issues"][0]["resolution"] == "repair"
    state = load_state(state_path)
    repaired = state.section_briefs["applications"]
    assert repaired.summary.startswith("Repaired ")
    assert repaired.title == "Applications"
    assert repaired.guiding_questions == []
    assert repaired.sources[0].title == "Source"
    assert "evidence_repair" in state.completed_stages


def test_verifier_hard_failure_preserves_state(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    runner = StubAgentRunner(verification_reports=[fatal_report()])

    with pytest.raises(DeepResearchError, match="Source coverage failed"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=state_path,
        )

    state = load_state(state_path)
    assert state.verification_reports[-1].status == "failed"
    assert state.final_payload is None


def test_fatal_report_can_preserve_other_issue_resolutions(tmp_path: Path) -> None:
    report = VerificationReport(
        status="failed",
        issues=[
            fatal_report().issues[0],
            repair_report("applications").issues[0],
        ],
        notes=None,
    )
    runner = StubAgentRunner(verification_reports=[report])

    with pytest.raises(DeepResearchError, match="Source coverage failed"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=tmp_path / "report.research.json",
        )

    names = [name for name, _ in runner.calls]
    assert names.count("VerifierAgent") == 1
    assert "EvidenceRepairAgent" not in names


def test_warning_does_not_block_synthesis(tmp_path: Path) -> None:
    warning_report = VerificationReport(
        status="accepted",
        issues=[
            VerificationIssue(
                section_id="applications",
                code="minor-wording",
                message="One sentence could be clearer.",
                severity="warning",
                resolution="none",
                required_change="No change is required.",
            )
        ],
        notes=None,
    )
    runner = StubAgentRunner(verification_reports=[warning_report])
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=runner,
        state_path=tmp_path / "report.research.json",
    )
    names = [name for name, _ in runner.calls]
    assert "SynthesisAgent" in names
    assert "EvidenceRepairAgent" not in names
    assert "TargetedResearchAgent" not in names


def test_mixed_repair_and_research_stops_for_approval_then_recovers(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    mixed_report = VerificationReport(
        status="follow_up",
        issues=[
            repair_report("foundations").issues[0],
            research_report("applications").issues[0],
        ],
        notes=None,
    )
    runner = StubAgentRunner(verification_reports=[mixed_report])

    with pytest.raises(ResearchApprovalRequired, match="allow-paid-follow-up"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=state_path,
        )

    state = load_state(state_path)
    assert "evidence_repair" in state.completed_stages
    assert "targeted_research" not in state.completed_stages
    assert state.final_payload is None
    assert "TargetedResearchAgent" not in [name for name, _ in runner.calls]

    recovery_runner = StubAgentRunner()
    with pytest.raises(ResearchApprovalRequired):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=recovery_runner,
        )
    assert recovery_runner.calls == []

    compendium = recover_compendium(
        state_path,
        config=ResearchConfig(),
        runner=recovery_runner,
        allow_paid_follow_up=True,
    )
    assert compendium.topic == "Quantum Computing Compendium"
    recovery_names = [name for name, _ in recovery_runner.calls]
    assert recovery_names == [
        "TargetedResearchAgent",
        "VerifierAgent",
        "SynthesisAgent",
    ]
    targeted_payload = json.loads(recovery_runner.calls[0][1])["request"]
    assert targeted_payload["topic"] == "Quantum Computing Compendium"
    assert targeted_payload["plan"]["primary_objective"] == (
        "Explain the field with sources."
    )
    assert len(targeted_payload["agenda"]["sections"]) == 3
    assert targeted_payload["sections"][0]["brief"]["section_id"] == "applications"
    assert targeted_payload["sections"][0]["issues"][0]["resolution"] == "research"
    finished = load_state(state_path)
    assert "targeted_research" in finished.completed_stages
    assert len(finished.verification_reports) == 2


def test_no_search_repair_rejects_a_new_source_url(
    tmp_path: Path,
) -> None:
    class NewSourceRepairRunner(StubAgentRunner):
        def _output_for(self, name: str, input_payload: str) -> Any:
            output = super()._output_for(name, input_payload)
            if name == "EvidenceRepairAgent":
                output.revisions[0].findings[0].source_urls = [
                    "https://new.example/source"
                ]
            return output

    runner = NewSourceRepairRunner(verification_reports=[repair_report("applications")])
    with pytest.raises(ValueError, match="not in the prior brief"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=tmp_path / "report.research.json",
        )
    assert [name for name, _ in runner.calls].count("EvidenceRepairAgent") == 3
    assert "SynthesisAgent" not in [name for name, _ in runner.calls]


def test_interrupted_targeted_research_recovers_with_next_attempt(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    with pytest.raises(ResearchApprovalRequired):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=StubAgentRunner(
                verification_reports=[research_report("applications")]
            ),
            state_path=state_path,
        )

    class InterruptedTargetedRunner(StubAgentRunner):
        async def run(
            self,
            agent: Any,
            input_payload: str,
            *,
            max_turns: int,
        ) -> AgentRunResult:
            if agent.name == "TargetedResearchAgent":
                self.calls.append((agent.name, input_payload))
                raise WorkflowInterrupted("targeted research interrupted")
            return await super().run(
                agent,
                input_payload,
                max_turns=max_turns,
            )

    with pytest.raises(WorkflowInterrupted, match="targeted research interrupted"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=InterruptedTargetedRunner(),
            allow_paid_follow_up=True,
        )

    resumed_runner = StubAgentRunner()
    recover_compendium(
        state_path,
        config=ResearchConfig(),
        runner=resumed_runner,
        allow_paid_follow_up=True,
    )
    names = [name for name, _ in resumed_runner.calls]
    assert names == [
        "TargetedResearchAgent",
        "VerifierAgent",
        "SynthesisAgent",
    ]
    state = load_state(state_path)
    invocation_id = f"{state.run_id}:targeted_research"
    assert state.attempt_counts[invocation_id] == 2


def test_targeted_research_updates_same_url_provenance(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    with pytest.raises(ResearchApprovalRequired):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=StubAgentRunner(
                verification_reports=[research_report("applications")]
            ),
            state_path=state_path,
        )

    class ProvenanceTargetedRunner(StubAgentRunner):
        def _output_for(self, name: str, input_payload: str) -> Any:
            output = super()._output_for(name, input_payload)
            if name == "TargetedResearchAgent":
                source = output.revisions[0].sources[0]
                source.revision = "commit-123"
                source.accessed_at = "2026-08-29T12:00:00-07:00"
            return output

    recover_compendium(
        state_path,
        config=ResearchConfig(),
        runner=ProvenanceTargetedRunner(),
        allow_paid_follow_up=True,
    )

    state = load_state(state_path)
    source = state.section_briefs["applications"].sources[0]
    assert source.revision == "commit-123"
    assert source.accessed_at == "2026-08-29T12:00:00-07:00"


def test_final_verification_preserves_repair_resolution_and_is_terminal(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    runner = StubAgentRunner(
        verification_reports=[
            repair_report("applications"),
            repair_report("applications", message="Gap remains."),
        ]
    )
    with pytest.raises(DeepResearchError, match="Final research verification failed"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=state_path,
        )
    names = [name for name, _ in runner.calls]
    assert names.count("EvidenceRepairAgent") == 1
    assert names.count("VerifierAgent") == 2
    assert "SynthesisAgent" not in names
    final_report = load_state(state_path).verification_reports[-1]
    assert final_report.status == "follow_up"
    assert final_report.issues[0].resolution == "repair"


def test_recovery_resumes_from_next_incomplete_stage(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    first_runner = StubAgentRunner()
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=first_runner,
        state_path=state_path,
    )

    state = load_state(state_path)
    state.final_payload = None
    state.completed_stages.remove("synthesis")
    synthesis_invocation = f"{state.run_id}:synthesis"
    state.agent_stages.pop(synthesis_invocation)
    state_path.write_text(
        state.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    trace_path = _contract_trace_path(state_path)
    original_trace = load_trace_jsonl(trace_path)
    reduced_trace = NormalizedTrace(
        tuple(
            event
            for event in original_trace.events
            if str(event.semantic.agent_id) != "agent:SynthesisAgent"
        )
    )
    write_trace_jsonl(trace_path, reduced_trace)
    closure = _load_trace_closure(state_path)
    reduced_closure = replace(
        closure,
        frontier=TraceFrontier.from_trace(reduced_trace),
        attempts=tuple(
            item
            for item in closure.attempts
            if item.attempt.invocation_id != synthesis_invocation
        ),
    )
    _contract_trace_closure_path(state_path).write_text(
        TraceClosureManifest((reduced_closure,)).to_json() + "\n",
        encoding="utf-8",
    )

    second_runner = StubAgentRunner()
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=second_runner,
        state_path=state_path,
    )

    assert [name for name, _ in second_runner.calls] == ["SynthesisAgent"]
    trace_lines = trace_path.read_text(encoding="utf-8")
    assert trace_lines.count('"event_type":"agent.completed"') == 7


def test_completed_recovery_reassesses_matching_trace_without_agent_calls(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    runner = StubAgentRunner()

    with mock.patch(
        "compendiumscribe.research.agents_workflow.orchestrator._evaluate_contract_run",
        wraps=_evaluate_contract_run,
    ) as evaluate:
        compendium = recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=runner,
        )

    assert compendium.topic == "Quantum Computing Compendium"
    assert runner.calls == []
    evaluate.assert_called_once()


def test_progressed_recovery_requires_trace(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    _contract_trace_path(state_path).unlink()

    with pytest.raises(DeepResearchError, match="without trace evidence"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=StubAgentRunner(),
        )


def test_progressed_recovery_requires_trace_closure_before_agent_calls(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    _contract_trace_closure_path(state_path).unlink()
    runner = StubAgentRunner()

    with pytest.raises(DeepResearchError, match="without trace-closure evidence"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=runner,
        )

    assert runner.calls == []


def test_progressed_recovery_rejects_malformed_trace_closure(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    _contract_trace_closure_path(state_path).write_text(
        "not-json\n",
        encoding="utf-8",
    )
    runner = StubAgentRunner()

    with pytest.raises(DeepResearchError, match="Cannot recover"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=runner,
        )

    assert runner.calls == []


def test_progressed_recovery_rejects_legacy_trace_closure_manifest(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    closure_path = _contract_trace_closure_path(state_path)
    payload = json.loads(closure_path.read_text(encoding="utf-8"))
    payload["version"] = "2"
    closure_path.write_text(json.dumps(payload), encoding="utf-8")
    runner = StubAgentRunner()

    with pytest.raises(
        DeepResearchError,
        match="Unsupported trace-closure manifest version `2`",
    ):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=runner,
        )

    assert runner.calls == []


def test_progressed_recovery_rejects_mismatched_trace_closure(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    closure_path = _contract_trace_closure_path(state_path)
    payload = json.loads(closure_path.read_text(encoding="utf-8"))
    payload["closures"][0]["run_id"] = "different-run"
    closure_path.write_text(json.dumps(payload), encoding="utf-8")
    runner = StubAgentRunner()

    with pytest.raises(DeepResearchError, match="exactly one matching run"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=runner,
        )

    assert runner.calls == []


@pytest.mark.parametrize("contents", ["", "not-json\n"])
def test_progressed_recovery_rejects_empty_or_malformed_trace(
    tmp_path: Path,
    contents: str,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    _contract_trace_path(state_path).write_text(contents, encoding="utf-8")

    with pytest.raises(DeepResearchError, match="empty trace|Cannot recover"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=StubAgentRunner(),
        )


def test_progressed_recovery_rejects_mismatched_plan_digest(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    state = load_state(state_path)
    state.config_snapshot["plan_digest"] = "sha256:mismatched-plan"
    save_state(state_path, state)

    with pytest.raises(
        DeepResearchError,
        match="different Contract4Agents plan digest",
    ):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=StubAgentRunner(),
        )


def test_recovery_rejects_state_without_auditable_plan_digest(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    save_state(
        state_path,
        ResearchRunState(
            topic="Legacy state",
            title="Legacy state",
            completed_stages=["planning"],
        ),
    )

    with pytest.raises(
        DeepResearchError,
        match="different Contract4Agents plan digest",
    ):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=StubAgentRunner(),
        )


def test_completed_recovery_rejects_trace_past_closure_frontier(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    trace_path = _contract_trace_path(state_path)
    trace = load_trace_jsonl(trace_path)
    incomplete = NormalizedTrace(
        tuple(
            event
            for event in trace.events
            if not (
                event.event_type == "output.accepted"
                and str(event.semantic.agent_id) == "agent:SynthesisAgent"
            )
        )
    )
    write_trace_jsonl(trace_path, incomplete)

    with pytest.raises(DeepResearchError, match="closure frontier does not match"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=StubAgentRunner(),
        )


def test_pristine_state_can_start_without_trace(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    save_state(
        state_path,
        ResearchRunState(topic="Quantum Computing", title="Quantum Computing"),
    )
    assert not _contract_trace_path(state_path).exists()

    result = recover_compendium(
        state_path,
        config=ResearchConfig(),
        runner=StubAgentRunner(),
    )

    assert result.topic == "Quantum Computing Compendium"
    assert _contract_trace_path(state_path).exists()


def test_invalid_citation_ids_fail_before_rendering(tmp_path: Path) -> None:
    bad_payload = sample_payload()
    bad_payload.sections[0].insights[0].citations = ["C99"]
    runner = StubAgentRunner(final_payload=bad_payload)

    with pytest.raises(ValueError, match="unknown citation IDs: C99"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=tmp_path / "report.research.json",
        )


def test_synthesis_web_search_fails_contract_run_spec(tmp_path: Path) -> None:
    class BadSynthesisRunner(StubAgentRunner):
        async def run(
            self,
            agent: Any,
            input_payload: str,
            *,
            max_turns: int,
        ) -> AgentRunResult:
            result = await super().run(
                agent,
                input_payload,
                max_turns=max_turns,
            )
            if agent.name == "SynthesisAgent":
                result.raw_result.raw_responses[0].output = [
                    {"type": "web_search_call"}
                ]
            return result

    with pytest.raises(DeepResearchError, match="trace conformance"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=BadSynthesisRunner(),
            state_path=tmp_path / "report.research.json",
        )


def test_planner_web_search_records_violation_and_blocks_recovery(
    tmp_path: Path,
) -> None:
    class BadPlannerRunner(StubAgentRunner):
        async def run(
            self,
            agent: Any,
            input_payload: str,
            *,
            max_turns: int,
        ) -> AgentRunResult:
            result = await super().run(
                agent,
                input_payload,
                max_turns=max_turns,
            )
            if agent.name == "PlannerAgent":
                result.raw_result.raw_responses[0].output = [
                    {"type": "web_search_call"}
                ]
            return result

    state_path = tmp_path / "report.research.json"
    with pytest.raises(DeepResearchError, match="trace conformance"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=BadPlannerRunner(),
            state_path=state_path,
        )
    trace = load_trace_jsonl(_contract_trace_path(state_path))
    assert any(event.event_type == "capability.undeclared" for event in trace.events)
    assert trace.events[-1].event_type == "attempt.selected"
    assert trace.events[-1].data["outcome"] == "failed"

    recovery_runner = StubAgentRunner()
    with pytest.raises(DeepResearchError, match="trace conformance"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=recovery_runner,
        )
    assert recovery_runner.calls == []


@pytest.mark.parametrize("item_type", ["file_search_call", "future_hosted_call"])
def test_unsupported_or_unknown_hosted_call_fails_closed(
    tmp_path: Path,
    item_type: str,
) -> None:
    class UnsupportedHostedCallRunner(StubAgentRunner):
        async def run(
            self,
            agent: Any,
            input_payload: str,
            *,
            max_turns: int,
        ) -> AgentRunResult:
            result = await super().run(
                agent,
                input_payload,
                max_turns=max_turns,
            )
            if agent.name == "PlannerAgent":
                result.raw_result.raw_responses[0].output = [{"type": item_type}]
            return result

    state_path = tmp_path / "report.research.json"
    with pytest.raises(DeepResearchError, match="trace conformance"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=UnsupportedHostedCallRunner(),
            state_path=state_path,
        )

    trace = load_trace_jsonl(_contract_trace_path(state_path))
    violation = next(
        event for event in trace.events if event.event_type == "capability.undeclared"
    )
    assert violation.event_type == "capability.undeclared"
    assert item_type in violation.data["reason"]
    assert str(violation.data["provider_tool"]).startswith("openai.")
    assert trace.events[-1].event_type == "attempt.selected"
    assert trace.events[-1].data["outcome"] == "failed"


def test_host_dispatched_call_is_not_classified_as_hosted_capability(
    tmp_path: Path,
) -> None:
    class HostDispatchedCallRunner(StubAgentRunner):
        async def run(
            self,
            agent: Any,
            input_payload: str,
            *,
            max_turns: int,
        ) -> AgentRunResult:
            result = await super().run(
                agent,
                input_payload,
                max_turns=max_turns,
            )
            if agent.name == "PlannerAgent":
                result.raw_result.raw_responses[0].output = [{"type": "function_call"}]
            return result

    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=HostDispatchedCallRunner(),
        state_path=state_path,
    )

    trace = load_trace_jsonl(_contract_trace_path(state_path))
    assert not any(
        event.event_type == "capability.undeclared" for event in trace.events
    )


def test_exception_responses_survive_retry_and_selected_success(
    tmp_path: Path,
) -> None:
    class InterruptedManagerRunner(StubAgentRunner):
        def __init__(self) -> None:
            super().__init__()
            self.interrupted = False

        async def run(
            self,
            agent: Any,
            input_payload: str,
            *,
            max_turns: int,
        ) -> AgentRunResult:
            if agent.name == "ResearchManagerAgent" and not self.interrupted:
                self.interrupted = True
                self.calls.append((agent.name, input_payload))
                exception = RuntimeError("manager interrupted")
                exception.run_data = SimpleNamespace(
                    raw_responses=[
                        SimpleNamespace(
                            response_id="resp_interrupted",
                            output=[{"type": "web_search_call"}],
                        )
                    ]
                )
                raise exception
            return await super().run(
                agent,
                input_payload,
                max_turns=max_turns,
            )

    state_path = tmp_path / "report.research.json"
    runner = InterruptedManagerRunner()
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=runner,
        state_path=state_path,
    )

    interrupted_trace = load_trace_jsonl(_contract_trace_path(state_path))
    interrupted_tool = next(
        event
        for event in interrupted_trace.events
        if event.event_type == "tool.completed"
        and event.provider.run_id == "resp_interrupted"
    )
    assert interrupted_tool.data["attempt"]["number"] == 1

    completed_state = load_state(state_path)
    manager_stage = completed_state.agent_stages[
        f"{completed_state.run_id}:research_agenda"
    ]
    assert manager_stage.attempt_number == 2
    assert manager_stage.retry_of == (
        f"{completed_state.run_id}:research_agenda:attempt:1"
    )
    completed_trace = load_trace_jsonl(_contract_trace_path(state_path))
    manager_selections = [
        event
        for event in completed_trace.events
        if event.event_type == "attempt.selected"
        and event.data["attempt"]["invocation_id"]
        == f"{completed_state.run_id}:research_agenda"
    ]
    assert len(manager_selections) == 1
    assert manager_selections[0].data["attempt"]["number"] == 2


def test_schema_invalid_attempt_remains_evidence_without_poisoning_retry(
    tmp_path: Path,
) -> None:
    class InvalidPlannerRunner(StubAgentRunner):
        def __init__(self) -> None:
            super().__init__()
            self.returned_invalid_output = False

        def _output_for(self, name: str, input_payload: str) -> Any:
            if name == "PlannerAgent" and not self.returned_invalid_output:
                self.returned_invalid_output = True
                return {"title": "Incomplete"}
            return super()._output_for(name, input_payload)

    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=InvalidPlannerRunner(),
        state_path=state_path,
    )

    invalid_trace = load_trace_jsonl(_contract_trace_path(state_path))
    schema_failure = next(
        event
        for event in invalid_trace.events
        if event.event_type == "output.schema_failed"
    )
    assert schema_failure.data["attempt"]["number"] == 1
    assert not any(
        event.event_type == "attempt.selected"
        and event.data["attempt"]["attempt_id"]
        == schema_failure.data["attempt"]["attempt_id"]
        for event in invalid_trace.events
    )
    completed_state = load_state(state_path)
    planner_stage = completed_state.agent_stages[f"{completed_state.run_id}:planning"]
    assert planner_stage.attempt_number == 2
    assert planner_stage.retry_of == f"{completed_state.run_id}:planning:attempt:1"
    assert completed_state.run_spec_result["status"] == "passed"


def test_runner_exception_fails_out_after_planner_attempt_limit(tmp_path: Path) -> None:
    class FailingPlannerRunner(StubAgentRunner):
        async def run(
            self,
            agent: Any,
            input_payload: str,
            *,
            max_turns: int,
        ) -> AgentRunResult:
            if agent.name == "PlannerAgent":
                self.calls.append((agent.name, input_payload))
                raise RuntimeError("planner unavailable")
            return await super().run(
                agent,
                input_payload,
                max_turns=max_turns,
            )

    state_path = tmp_path / "report.research.json"
    runner = FailingPlannerRunner()
    with pytest.raises(RuntimeError, match="planner unavailable"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=state_path,
        )

    assert len(runner.calls) == 3
    failed_state = load_state(state_path)
    invocation_id = f"{failed_state.run_id}:planning"
    assert failed_state.attempt_counts[invocation_id] == 3
    trace = load_trace_jsonl(_contract_trace_path(state_path))
    selection = trace.events[-1]
    assert selection.event_type == "attempt.selected"
    assert selection.data["outcome"] == "failed"
    assert selection.data["attempt"]["number"] == 3

    recovery_runner = StubAgentRunner()
    with pytest.raises(DeepResearchError, match="failed after 3 attempts"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=recovery_runner,
        )
    assert recovery_runner.calls == []


def test_schema_failure_fails_out_after_planner_attempt_limit(tmp_path: Path) -> None:
    class InvalidPlannerRunner(StubAgentRunner):
        def _output_for(self, name: str, input_payload: str) -> Any:
            if name == "PlannerAgent":
                return {"title": "Incomplete"}
            return super()._output_for(name, input_payload)

    state_path = tmp_path / "report.research.json"
    runner = InvalidPlannerRunner()
    with pytest.raises(ValidationError):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=state_path,
        )

    assert len(runner.calls) == 3
    trace = load_trace_jsonl(_contract_trace_path(state_path))
    assert (
        sum(event.event_type == "output.schema_failed" for event in trace.events) == 3
    )
    selection = trace.events[-1]
    assert selection.event_type == "attempt.selected"
    assert selection.data["outcome"] == "failed"
    assert selection.data["attempt"]["number"] == 3


def test_run_spec_rejects_stage_evidence_without_agent_identity(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=StubAgentRunner(),
        state_path=state_path,
    )
    trace_path = _contract_trace_path(state_path)
    trace = load_trace_jsonl(trace_path)
    events = []
    for event in trace.events:
        if (
            event.event_type == "stage.completed"
            and str(event.semantic.agent_id) == "agent:SynthesisAgent"
        ):
            event = replace(
                event,
                semantic=replace(event.semantic, agent_id=None),
            )
        events.append(event)
    altered_trace = NormalizedTrace(tuple(events))
    write_trace_jsonl(trace_path, altered_trace)
    closure = _load_trace_closure(state_path)
    _contract_trace_closure_path(state_path).write_text(
        TraceClosureManifest(
            (replace(closure, frontier=TraceFrontier.from_trace(altered_trace)),)
        ).to_json()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        DeepResearchError,
        match=r"run_spec:CompendiumResearch: unverified",
    ):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=StubAgentRunner(),
        )
    failed_state = load_state(state_path)
    assert failed_state.run_spec_selection["evidence_refs"]
    assert failed_state.run_spec_result["status"] == "unverified"


def test_synthesis_citations_are_hydrated_from_source_ledger(
    tmp_path: Path,
) -> None:
    payload = sample_payload()
    payload.citations[0].title = "Model-supplied source"
    payload.citations[0].url = "https://wrong.example.com"
    runner = StubAgentRunner(final_payload=payload)
    state_path = tmp_path / "report.research.json"

    compendium = build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=runner,
        state_path=state_path,
    )

    assert compendium.citations[0].title == "Source"
    assert compendium.citations[0].url == "https://example.com/source"
    state = load_state(state_path)
    assert state.final_payload is not None
    assert state.final_payload.citations[0].title == "Source"
    assert state.final_payload.citations[0].url == "https://example.com/source"


def test_agent_workflow_records_costs_and_progress(tmp_path: Path) -> None:
    captured = []
    tracker = CostTracker(
        path=tmp_path / "report.costs.json",
        pricing=CostPricing(
            input_per_1m_usd=None,
            cached_input_per_1m_usd=None,
            output_per_1m_usd=None,
        ),
    )

    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(progress_callback=captured.append),
        runner=StubAgentRunner(),
        state_path=tmp_path / "report.research.json",
        cost_tracker=tracker,
    )

    costs = json.loads((tmp_path / "report.costs.json").read_text())
    assert len(costs["steps"]) == 7
    assert {step["model"] for step in costs["steps"]} == {
        "gpt-5.6-sol",
        "gpt-5.6-terra",
    }
    assert costs["totals"]["input_tokens"] == 700
    assert costs["totals"]["tool_calls"]["web_search_call"] == 4
    phases = [event.phase for event in captured]
    assert "planning" in phases
    assert "research_agenda" in phases
    assert "section_research" in phases
    assert "verification" in phases
    assert "synthesis" in phases
    assert "completion" in phases


def test_openai_agent_runner_passes_client_through_run_config(
    monkeypatch,
) -> None:
    client = object()
    captured: dict[str, Any] = {}

    async def fake_run(
        agent: Any,
        input_payload: str,
        *,
        max_turns: int,
        run_config: Any = None,
        **_kwargs: Any,
    ) -> Any:
        captured["agent"] = agent
        captured["input_payload"] = input_payload
        captured["max_turns"] = max_turns
        captured["run_config"] = run_config
        return SimpleNamespace(final_output={"ok": True}, raw_responses=[])

    monkeypatch.setattr("agents.Runner.run", fake_run)

    result = asyncio.run(
        OpenAIAgentRunner(openai_client=client).run(
            SimpleNamespace(name="Agent"),
            "payload",
            max_turns=3,
        )
    )

    assert result.final_output == {"ok": True}
    assert captured["input_payload"] == "payload"
    assert captured["max_turns"] == 3
    assert captured["run_config"] is not None
    assert getattr(captured["run_config"].model_provider, "_client") is client
