from __future__ import annotations

from typing import Any, TYPE_CHECKING
import time

from ..config import ResearchConfig
from ..errors import (
    DeepResearchError,
    ResearchCancelledError,
    ResearchTimeoutError,
)
from ..progress import emit_progress
from ..utils import coerce_optional_string, get_field

if TYPE_CHECKING:
    from ..cancellation import CancellationContext


__all__ = ["await_completion"]


def await_completion(
    client: Any,
    response: Any,
    config: ResearchConfig,
    cancel_ctx: "CancellationContext | None" = None,
):
    """Poll the OpenAI responses API until the run completes or fails."""
    attempts = 0
    emit_progress(
        config,
        phase="deep_research",
        status="in_progress",
        message="Polling for deep research completion.",
    )

    current = response
    start_time = time.monotonic()
    max_seconds = config.max_poll_time_minutes * 60

    while True:
        elapsed_seconds = int(time.monotonic() - start_time)
        if elapsed_seconds > max_seconds:
            raise ResearchTimeoutError(
                (
                    "Deep research did not complete within the "
                    f"{config.max_poll_time_minutes} minute limit."
                ),
                research_id=response.id,
            )

        time.sleep(config.polling_interval_seconds)
        attempts += 1
        elapsed_seconds = int(time.monotonic() - start_time)

        current = client.responses.retrieve(response.id)
        status = coerce_optional_string(get_field(current, "status"))

        if status == "completed":
            emit_progress(
                config,
                phase="deep_research",
                status="completed",
                message="Deep research run finished; decoding payload.",
                metadata={
                    "status": status,
                    "elapsed_seconds": elapsed_seconds,
                },
            )
            break

        if status == "cancelled":
            emit_progress(
                config,
                phase="deep_research",
                status="cancelled",
                message="Research cancelled.",
                metadata={"elapsed_seconds": elapsed_seconds},
            )
            raise ResearchCancelledError(
                "Research was cancelled by user.",
                research_id=response.id,
            )

        if status in {"failed", "error"}:
            raise DeepResearchError(
                f"Deep research run failed with status: {status}"
            )

        emit_progress(
            config,
            phase="deep_research",
            status="update",
            message="In progress...",
            metadata={
                "status": status,
                "poll_attempt": attempts,
                "elapsed_seconds": elapsed_seconds,
            },
        )

    return current
