from __future__ import annotations

from pathlib import Path

from .artifacts import ResearchRunState


def load_state(path: Path) -> ResearchRunState:
    return ResearchRunState.model_validate_json(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: ResearchRunState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        state.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = ["load_state", "save_state"]
