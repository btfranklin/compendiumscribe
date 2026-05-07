from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from compendiumscribe.research.agents_workflow.artifacts import ResearchRunState
from compendiumscribe.research.agents_workflow.state import load_state, save_state


def test_save_state_writes_loadable_sidecar(tmp_path: Path) -> None:
    state_path = tmp_path / "report.research.json"
    state = ResearchRunState(
        topic="Atomic Recovery",
        title="Atomic Recovery",
        output_formats=["md"],
    )

    save_state(state_path, state)

    loaded = load_state(state_path)
    assert loaded.run_id == state.run_id
    assert loaded.topic == "Atomic Recovery"
    assert loaded.output_formats == ["md"]


def test_save_state_keeps_existing_sidecar_when_replace_fails(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "report.research.json"
    original = ResearchRunState(topic="Original", title="Original")
    updated = ResearchRunState(topic="Updated", title="Updated")
    save_state(state_path, original)
    original_payload = state_path.read_text(encoding="utf-8")

    with mock.patch(
        "compendiumscribe.research.agents_workflow.state.os.replace",
        side_effect=OSError("replace failed"),
    ):
        with pytest.raises(OSError, match="replace failed"):
            save_state(state_path, updated)

    assert state_path.read_text(encoding="utf-8") == original_payload
    assert load_state(state_path).topic == "Original"
    assert not list(tmp_path.glob(".report.research.json.*.tmp"))
