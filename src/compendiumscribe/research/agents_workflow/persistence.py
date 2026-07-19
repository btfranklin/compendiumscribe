from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
from uuid import uuid4


def atomic_write_text(path: Path, payload: str) -> None:
    """Durably replace one text file without exposing partial contents."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as output_file:
            output_file.write(payload)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temp_path, path)
    except Exception:
        with suppress(OSError):
            temp_path.unlink()
        raise


__all__ = ["atomic_write_text"]
