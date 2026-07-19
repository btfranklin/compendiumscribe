from __future__ import annotations

from pathlib import Path

from .artifacts import ResearchRunState
from .persistence import atomic_write_text


def load_state(path: Path) -> ResearchRunState:
    return ResearchRunState.model_validate_json(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: ResearchRunState) -> None:
    payload = state.model_dump_json(indent=2) + "\n"
    atomic_write_text(path, payload)


__all__ = ["load_state", "save_state"]
