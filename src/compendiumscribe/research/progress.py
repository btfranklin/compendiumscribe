from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .config import ResearchConfig

ProgressPhase = Literal[
    "planning",
    "prompt_composition",
    "deep_research",
    "trace",
    "completion",
]

ProgressStatus = Literal[
    "starting",
    "in_progress",
    "update",
    "completed",
    "error",
]


@dataclass(slots=True)
class ResearchProgress:
    """Represents a progress update emitted during the research workflow."""

    phase: ProgressPhase
    status: ProgressStatus
    message: str
    metadata: dict[str, Any] | None = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


def emit_progress(
    config: "ResearchConfig",
    *,
    phase: ProgressPhase,
    status: ProgressStatus,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    callback: Callable[[ResearchProgress], None] | None = getattr(
        config,
        "progress_callback",
        None,
    )
    if callback is None:
        return

    try:
        callback(
            ResearchProgress(
                phase=phase,
                status=status,
                message=message,
                metadata=metadata,
            )
        )
    except Exception:
        # Progress callbacks must never break the research workflow.
        return


__all__ = [
    "ProgressPhase",
    "ProgressStatus",
    "ResearchProgress",
    "emit_progress",
]
