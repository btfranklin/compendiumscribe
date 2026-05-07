from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
from uuid import uuid4

from .artifacts import ResearchRunState


def load_state(path: Path) -> ResearchRunState:
    return ResearchRunState.model_validate_json(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: ResearchRunState) -> None:
    payload = state.model_dump_json(indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as state_file:
            state_file.write(payload)
            state_file.flush()
            os.fsync(state_file.fileno())
        os.replace(temp_path, path)
    except Exception:
        with suppress(OSError):
            temp_path.unlink()
        raise


__all__ = ["load_state", "save_state"]
