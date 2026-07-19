from __future__ import annotations

from pathlib import Path
from unittest import mock

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


def test_trace_recorder_registers_one_processor(tmp_path: Path) -> None:
    team = build_research_agent_team(ResearchConfig())

    with mock.patch("agents.add_trace_processor") as add_trace_processor:
        recorder = ContractTraceRecorder(
            tmp_path / "report.research.trace.jsonl",
            run_id="run-1",
            ir=team.ir,
            plan=team.plan,
            append=False,
        )

    add_trace_processor.assert_called_once_with(recorder.processor)
