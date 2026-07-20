from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from contract4agents.tracing import TraceAttempt, TraceClosureManifest
import pytest

from compendiumscribe.research.agents_workflow.contract_trace import (
    ContractTraceRecorder,
)
from compendiumscribe.research.agents_workflow.agents import build_research_agent_team
from compendiumscribe.research.config import ResearchConfig


def test_trace_write_failure_preserves_file_and_recorder_state(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "report.research.trace.jsonl"
    team = build_research_agent_team(ResearchConfig())
    recorder = ContractTraceRecorder(
        trace_path,
        tmp_path / "report.research.trace-closure.json",
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

    assert trace_path.read_text(encoding="utf-8") == original_payload
    assert [event.event_type for event in recorder.events] == ["agent.started"]
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
    closure = recorder.close()

    assert len(events) == 1
    receipt = events[0]
    assert receipt.event_type == "provider.response_batch.normalized"
    assert receipt.data["batch_id"] == attempt.attempt_id
    assert receipt.data["response_count"] == 0
    assert receipt.data["response_ids"] == ()
    assert closure is not None
    assert closure.context == recorder.context
    assert closure.attempts[0].attempt == attempt
    assert closure.attempts[0].response_status == "complete"
    manifest = TraceClosureManifest.load(closure_path)
    assert manifest.closures == (closure,)
    persisted_event = json.loads(trace_path.read_text(encoding="utf-8"))
    assert persisted_event["schema_version"] == "2"


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
