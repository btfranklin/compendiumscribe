from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

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
        "compendiumscribe.research.agents_workflow.persistence.os.replace",
        side_effect=OSError("replace failed"),
    ):
        with pytest.raises(OSError, match="replace failed"):
            save_state(state_path, updated)

    assert state_path.read_text(encoding="utf-8") == original_payload
    assert load_state(state_path).topic == "Original"
    assert not list(tmp_path.glob(".report.research.json.*.tmp"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verification_status", "unknown"),
        ("verification_severity", "critical"),
        ("brief_source_status", "archived"),
        ("ledger_status", "archived"),
    ],
)
def test_load_state_rejects_invalid_portable_artifact_values(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    state_path = tmp_path / "report.research.json"
    payload = ResearchRunState(topic="Invalid state").model_dump(mode="json")
    payload["verification"] = {
        "status": value if field == "verification_status" else "accepted",
        "issues": [
            {
                "section_id": None,
                "message": "Check",
                "severity": value if field == "verification_severity" else "warning",
                "suggested_follow_up": None,
            }
        ],
        "follow_up_section_ids": [],
        "notes": None,
    }
    payload["section_briefs"] = {
        "S01": {
            "section_id": "S01",
            "title": "Section",
            "summary": "Summary",
            "key_terms": [],
            "guiding_questions": [],
            "findings": [],
            "sources": [
                {
                    "title": "Source",
                    "url": "https://example.com",
                    "publisher": None,
                    "published_at": None,
                    "summary": None,
                    "credibility_notes": None,
                    "status": value if field == "brief_source_status" else "cited",
                }
            ],
            "open_questions": [],
        }
    }
    payload["ledger"] = {
        "entries": [
            {
                "id": "C01",
                "title": "Source",
                "url": "https://example.com",
                "publisher": None,
                "published_at": None,
                "summary": None,
                "credibility_notes": None,
                "status": value if field == "ledger_status" else "cited",
                "section_ids": ["S01"],
            }
        ]
    }
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_state(state_path)
