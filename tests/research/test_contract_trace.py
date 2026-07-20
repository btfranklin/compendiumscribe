from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from contract4agents.tracing import TraceAttempt, TraceClosureManifest
import pytest

from compendiumscribe.research.agents_workflow.contract_trace import (
    ContractTraceRecorder,
)
from compendiumscribe.research.agents_workflow.agents import build_research_agent_team
from compendiumscribe.research.config import ResearchConfig


def test_trace_write_failure_preserves_the_accepted_capture_frontier(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "report.research.trace.jsonl"
    closure_path = tmp_path / "report.research.trace-closure.json"
    team = build_research_agent_team(ResearchConfig())
    recorder = ContractTraceRecorder(
        trace_path,
        closure_path,
        run_id="run-1",
        ir=team.ir,
        plan=team.plan,
        append=False,
    )
    recorder.record("agent.started", agent_name="PlannerAgent")
    original_payload = trace_path.read_text(encoding="utf-8")

    with mock.patch(
        "contract4agents.tracing._io.os.replace",
        side_effect=OSError("replace failed"),
    ):
        with pytest.raises(OSError, match="replace failed"):
            recorder.record("agent.completed", agent_name="PlannerAgent")

    snapshot = recorder.checkpoint()

    assert trace_path.read_text(encoding="utf-8") == original_payload
    assert [event.event_type for event in recorder.events] == ["agent.started"]
    assert snapshot.trace == recorder.trace
    assert snapshot.closure.frontier.event_count == 1
    assert TraceClosureManifest.load(closure_path).closures == (snapshot.closure,)
    assert not list(tmp_path.glob(".report.research.trace.jsonl.*.tmp"))
    recorder.close()


def test_trace_recorders_reuse_process_router_with_disposable_sessions(
    tmp_path: Path,
) -> None:
    team = build_research_agent_team(ResearchConfig())

    with mock.patch("agents.add_trace_processor") as add_trace_processor:
        first = ContractTraceRecorder(
            tmp_path / "first.trace.jsonl",
            tmp_path / "first.trace-closure.json",
            run_id="run-1",
            ir=team.ir,
            plan=team.plan,
            append=False,
        )
        first_session = first.session
        first.close()
        second = ContractTraceRecorder(
            tmp_path / "second.trace.jsonl",
            tmp_path / "second.trace-closure.json",
            run_id="run-2",
            ir=team.ir,
            plan=team.plan,
            append=False,
        )
        second_session = second.session
        second.close()

    add_trace_processor.assert_not_called()
    assert first_session is not second_session
    assert first_session.router is second_session.router
    assert first_session.context.run_id == "run-1"
    assert second_session.context.run_id == "run-2"


def test_session_close_detaches_router_trace_without_fabricating_completion(
    tmp_path: Path,
) -> None:
    team = build_research_agent_team(ResearchConfig())
    recorder = ContractTraceRecorder(
        tmp_path / "report.trace.jsonl",
        tmp_path / "report.trace-closure.json",
        run_id="run-1",
        ir=team.ir,
        plan=team.plan,
        append=False,
    )
    attempt = TraceAttempt("planning", "planning-attempt-1", 1)
    provider_trace = SimpleNamespace(trace_id="provider-trace-1")

    with recorder.bind_attempt(attempt, agent_name="PlannerAgent"):
        recorder.session.router.on_trace_start(provider_trace)

    assert recorder.session.router.active_trace_count == 1
    snapshot = recorder.close()

    assert recorder.session.router.active_trace_count == 0
    assert snapshot.closure.status == "incomplete"
    assert snapshot.closure.attempts[0].lifecycle_status == "incomplete"


def test_checkpoint_resume_preserves_retry_chain_without_rebinding_prior_attempt(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "report.trace.jsonl"
    closure_path = tmp_path / "report.trace-closure.json"
    team = build_research_agent_team(ResearchConfig())
    first = ContractTraceRecorder(
        trace_path,
        closure_path,
        run_id="run-1",
        ir=team.ir,
        plan=team.plan,
        append=False,
    )
    attempt_1 = TraceAttempt("planning", "planning-attempt-1", 1)
    with first.bind_attempt(attempt_1, agent_name="PlannerAgent"):
        first.normalize_response_events(
            (),
            agent_name="PlannerAgent",
            attempt=attempt_1,
        )
    first_snapshot = first.checkpoint()
    first.close()

    resumed = ContractTraceRecorder(
        trace_path,
        closure_path,
        run_id="run-1",
        ir=team.ir,
        plan=team.plan,
        append=True,
    )
    attempt_2 = TraceAttempt(
        "planning",
        "planning-attempt-2",
        2,
        retry_of=attempt_1.attempt_id,
    )
    with pytest.raises(ValueError, match="sealed by prior closure evidence"):
        with resumed.bind_attempt(attempt_1, agent_name="PlannerAgent"):
            pass
    with resumed.bind_attempt(attempt_2, agent_name="PlannerAgent"):
        resumed.normalize_response_events(
            (),
            agent_name="PlannerAgent",
            attempt=attempt_2,
        )
    resumed_snapshot = resumed.close()

    assert resumed_snapshot.trace.events[: len(first_snapshot.trace.events)] == (
        first_snapshot.trace.events
    )
    assert [item.attempt for item in resumed_snapshot.closure.attempts] == [
        attempt_1,
        attempt_2,
    ]
    assert resumed_snapshot.closure.frontier.event_count == len(
        resumed_snapshot.trace.events
    )


def test_resumed_session_can_select_a_checkpointed_attempt(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "report.trace.jsonl"
    closure_path = tmp_path / "report.trace-closure.json"
    team = build_research_agent_team(ResearchConfig())
    first = ContractTraceRecorder(
        trace_path,
        closure_path,
        run_id="run-1",
        ir=team.ir,
        plan=team.plan,
        append=False,
    )
    attempt = TraceAttempt("planning", "planning-attempt-1", 1)
    with first.bind_attempt(attempt, agent_name="PlannerAgent"):
        first.normalize_response_events(
            (),
            agent_name="PlannerAgent",
            attempt=attempt,
        )
    first_snapshot = first.checkpoint()
    first.close()

    resumed = ContractTraceRecorder(
        trace_path,
        closure_path,
        run_id="run-1",
        ir=team.ir,
        plan=team.plan,
        append=True,
    )
    selection = resumed.record_terminal_attempt(
        agent_name="PlannerAgent",
        attempt=attempt,
        outcome="failed",
    )
    snapshot = resumed.close()

    assert selection.event_type == "attempt.selected"
    assert snapshot.trace.events[-1] == selection
    assert snapshot.closure.frontier.event_count == (
        first_snapshot.closure.frontier.event_count + 1
    )
    assert snapshot.closure.status == first_snapshot.closure.status


def test_zero_response_batch_emits_receipt_and_persists_closure_manifest(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "report.research.trace.jsonl"
    closure_path = tmp_path / "report.research.trace-closure.json"
    team = build_research_agent_team(ResearchConfig())
    recorder = ContractTraceRecorder(
        trace_path,
        closure_path,
        run_id="run-1",
        ir=team.ir,
        plan=team.plan,
        append=False,
    )
    attempt = TraceAttempt(
        invocation_id="planning",
        attempt_id="planning-attempt-1",
        number=1,
    )

    with recorder.bind_attempt(attempt, agent_name="PlannerAgent"):
        events = recorder.normalize_response_events(
            (),
            agent_name="PlannerAgent",
            attempt=attempt,
        )
    snapshot = recorder.close()
    closure = snapshot.closure

    assert len(events) == 1
    receipt = events[0]
    assert receipt.event_type == "provider.response_batch.normalized"
    assert receipt.data["batch_id"] == attempt.attempt_id
    assert receipt.data["response_count"] == 0
    assert receipt.data["response_ids"] == ()
    assert closure.context == recorder.context
    assert closure.frontier.event_count == len(snapshot.trace.events)
    assert closure.attempts[0].attempt == attempt
    assert closure.attempts[0].response_status == "complete"
    manifest = TraceClosureManifest.load(closure_path)
    assert manifest.version == "1"
    assert manifest.closures == (closure,)
    persisted_event = json.loads(trace_path.read_text(encoding="utf-8"))
    assert persisted_event["schema_version"] == "1"


def test_closure_write_failure_preserves_prior_file_and_cleans_temporary_file(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "report.research.trace.jsonl"
    closure_path = tmp_path / "report.research.trace-closure.json"
    closure_path.write_text("prior closure\n", encoding="utf-8")
    team = build_research_agent_team(ResearchConfig())
    recorder = ContractTraceRecorder(
        trace_path,
        closure_path,
        run_id="run-1",
        ir=team.ir,
        plan=team.plan,
        append=False,
    )
    attempt = TraceAttempt(
        invocation_id="planning",
        attempt_id="planning-attempt-1",
        number=1,
    )
    with recorder.bind_attempt(attempt, agent_name="PlannerAgent"):
        recorder.normalize_response_events(
            (),
            agent_name="PlannerAgent",
            attempt=attempt,
        )

    with mock.patch(
        "compendiumscribe.research.agents_workflow.persistence.os.replace",
        side_effect=OSError("replace failed"),
    ):
        with pytest.raises(OSError, match="replace failed"):
            recorder.close()

    assert closure_path.read_text(encoding="utf-8") == "prior closure\n"
    assert recorder.closure is None
    assert not list(tmp_path.glob(".report.research.trace-closure.json.*.tmp"))
