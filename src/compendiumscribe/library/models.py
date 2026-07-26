from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LibraryEntry:
    """Discovery metadata derived from one OKF compendium concept."""

    id: str
    title: str
    description: str
    tags: tuple[str, ...]
    timestamp: datetime
    path: str


__all__ = ["LibraryEntry"]
