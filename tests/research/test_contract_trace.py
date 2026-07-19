from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from compendiumscribe.research.agents_workflow.contract_trace import (
    ContractTraceRecorder,
)


def test_trace_write_failure_preserves_file_and_recorder_state(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "report.research.trace.jsonl"
    recorder = ContractTraceRecorder(
        trace_path,
        run_id="run-1",
        contract_digest="sha256:" + "1" * 64,
        plan_digest="sha256:" + "2" * 64,
        append=False,
    )
    recorder.record("agent.started", agent_name="PlannerAgent")
    original_payload = trace_path.read_text(encoding="utf-8")

    with mock.patch(
        "compendiumscribe.research.agents_workflow.persistence.os.replace",
        side_effect=OSError("replace failed"),
    ):
        with pytest.raises(OSError, match="replace failed"):
            recorder.record("agent.completed", agent_name="PlannerAgent")

    assert trace_path.read_text(encoding="utf-8") == original_payload
    assert [event.event_type for event in recorder.events] == ["agent.started"]
    assert not list(tmp_path.glob(".report.research.trace.jsonl.*.tmp"))
