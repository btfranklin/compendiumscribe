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
    load_trace_jsonl,
    write_trace_jsonl,
)

from compendiumscribe.agent_contracts.generated.python import (
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    ResearchSection,
    SectionResearchBrief,
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
    _contract_trace_path,
    _evaluate_contract_run,
)
from compendiumscribe.research.config import ResearchConfig
from compendiumscribe.research.costs import CostPricing, CostTracker
from compendiumscribe.research.errors import (
    DeepResearchError,
    MissingConfigurationError,
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
        self.verification_reports = verification_reports or [accepted_report()]
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
        index = len(self.calls)
        response = SimpleNamespace(
            response_id=f"resp_{index}",
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
                    "VerifierAgent",
                }
                else []
            ),
        )
        output = self._output_for(name, input_payload)
        return AgentRunResult(
            final_output=output,
            raw_result=SimpleNamespace(raw_responses=[response]),
        )

    def _output_for(self, name: str, input_payload: str) -> Any:
        if name == "PlannerAgent":
            return sample_plan()
        if name == "ResearchManagerAgent":
            return sample_agenda()
        if name == "SectionResearchAgent":
            payload = json.loads(input_payload)
            return sample_brief(payload["section"]["id"])
        if name == "VerifierAgent":
            return self.verification_reports.pop(0)
        if name == "SynthesisAgent":
            return self.final_payload
        raise AssertionError(f"Unexpected agent: {name}")


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
        follow_up_section_ids=[],
        notes=None,
    )


def follow_up_report(
    *section_ids: str,
    message: str = "Needs follow-up.",
) -> VerificationReport:
    return VerificationReport(
        status="follow_up",
        issues=[
            VerificationIssue(
                section_id=section_ids[0] if section_ids else None,
                message=message,
                severity="warning",
                suggested_follow_up=None,
            )
        ],
        follow_up_section_ids=list(section_ids),
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
        output_formats=["md", "xml"],
    )

    assert compendium.topic == "Quantum Computing Compendium"
    assert compendium.sections[0].insights[0].citation_refs == ["C01"]
    assert state_path.exists()
    state = load_state(state_path)
    assert state.plan is not None
    assert state.agenda is not None
    assert set(state.section_briefs) == {"foundations", "applications"}
    assert state.ledger.entries[0].id == "C01"
    assert state.final_payload is not None
    assert state.config_snapshot["contract4agents_profile"] == "production"
    assert state.config_snapshot["contract_digest"].startswith("sha256:")
    assert state.config_snapshot["plan_digest"].startswith("sha256:")
    assert set(state.config_snapshot["resolved_models"].values()) == {"gpt-5.5"}
    trace_path = _contract_trace_path(state_path)
    assert trace_path.exists()
    loaded_trace = load_trace_jsonl(trace_path)
    _evaluate_contract_run(
        build_research_agent_team(ResearchConfig()),
        loaded_trace,
    )
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
            "tool:research.deep_web_search",
            "grant:SectionResearchAgent:research.deep_web_search",
        ),
        (
            "agent:VerifierAgent",
            "tool:research.web_search",
            "grant:VerifierAgent:research.web_search",
        ),
    }
    assert [name for name, _ in runner.calls] == [
        "PlannerAgent",
        "ResearchManagerAgent",
        "SectionResearchAgent",
        "SectionResearchAgent",
        "VerifierAgent",
        "SynthesisAgent",
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


def test_verifier_follow_up_reruns_only_targeted_section_once(
    tmp_path: Path,
) -> None:
    runner = StubAgentRunner(
        verification_reports=[
            VerificationReport(
                status="follow_up",
                follow_up_section_ids=["applications"],
                notes=None,
                issues=[
                    VerificationIssue(
                        section_id="applications",
                        message="Needs more source diversity.",
                        severity="warning",
                        suggested_follow_up=None,
                    )
                ],
            ),
            accepted_report(),
        ]
    )

    build_compendium(
        "Quantum Computing",
        config=ResearchConfig(),
        runner=runner,
        state_path=tmp_path / "report.research.json",
    )

    section_calls = [
        json.loads(payload)["section"]["id"]
        for name, payload in runner.calls
        if name == "SectionResearchAgent"
    ]
    assert section_calls == ["foundations", "applications", "applications"]


def test_verifier_hard_failure_preserves_state(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    runner = StubAgentRunner(
        verification_reports=[
            VerificationReport(
                status="failed",
                issues=[
                    VerificationIssue(
                        section_id=None,
                        message="Source coverage failed.",
                        severity="error",
                        suggested_follow_up=None,
                    )
                ],
                follow_up_section_ids=[],
                notes=None,
            )
        ]
    )

    with pytest.raises(DeepResearchError, match="Source coverage failed"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=state_path,
        )

    state = load_state(state_path)
    assert state.verification is not None
    assert state.verification.status == "failed"
    assert state.final_payload is None


def test_second_follow_up_fails_without_synthesis(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    runner = StubAgentRunner(
        verification_reports=[
            follow_up_report("applications", message="First gap."),
            follow_up_report("applications", message="Gap remains."),
        ]
    )

    with pytest.raises(DeepResearchError, match="bounded follow-up cycle"):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=state_path,
        )

    assert "SynthesisAgent" not in [name for name, _ in runner.calls]
    state = load_state(state_path)
    assert state.follow_up_done is True
    assert state.verification.status == "follow_up"
    assert state.final_payload is None

    recovery_runner = StubAgentRunner()
    with pytest.raises(DeepResearchError, match="bounded follow-up cycle"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=recovery_runner,
        )
    assert recovery_runner.calls == []


@pytest.mark.parametrize(
    ("section_ids", "message"),
    [
        ((), "without any section IDs"),
        (("missing",), "unknown follow-up section IDs"),
        (("applications", "applications"), "duplicate follow-up section IDs"),
    ],
)
def test_invalid_follow_up_targets_fail_before_rerun(
    tmp_path: Path,
    section_ids: tuple[str, ...],
    message: str,
) -> None:
    runner = StubAgentRunner(verification_reports=[follow_up_report(*section_ids)])

    with pytest.raises(DeepResearchError, match=message):
        build_compendium(
            "Quantum Computing",
            config=ResearchConfig(),
            runner=runner,
            state_path=tmp_path / "report.research.json",
        )

    assert [name for name, _ in runner.calls].count("VerifierAgent") == 1
    assert "SynthesisAgent" not in [name for name, _ in runner.calls]


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
    state_path.write_text(
        state.model_dump_json(indent=2) + "\n",
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
    trace_lines = _contract_trace_path(state_path).read_text(encoding="utf-8")
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
    production_team = build_research_agent_team(ResearchConfig())
    comparison_team = replace(
        production_team,
        plan=replace(production_team.plan, profile="comparison"),
    )
    comparison_config = ResearchConfig(contract4agents_profile="comparison")

    with mock.patch(
        "compendiumscribe.research.agents_workflow.orchestrator."
        "build_research_agent_team",
        return_value=comparison_team,
    ):
        with pytest.raises(
            DeepResearchError,
            match="different Contract4Agents plan digest",
        ):
            recover_compendium(
                state_path,
                config=comparison_config,
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


def test_completed_recovery_rejects_incomplete_trace(tmp_path: Path) -> None:
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

    with pytest.raises(DeepResearchError, match="assurance failed"):
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
    assert [event.event_type for event in trace.events][-1] == ("capability.undeclared")

    recovery_runner = StubAgentRunner()
    with pytest.raises(DeepResearchError, match="trace conformance"):
        recover_compendium(
            state_path,
            config=ResearchConfig(),
            runner=recovery_runner,
        )
    assert recovery_runner.calls == []


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
    assert len(costs["steps"]) == 6
    assert {step["model"] for step in costs["steps"]} == {"gpt-5.5"}
    assert costs["totals"]["input_tokens"] == 600
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
