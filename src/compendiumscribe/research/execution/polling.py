from __future__ import annotations

from typing import Any
import time

from ..config import ResearchConfig
from ..errors import DeepResearchError
from ..progress import emit_progress
from ..utils import coerce_optional_string, get_field


__all__ = ["await_completion"]


def await_completion(
    client: Any,
    response: Any,
    config: ResearchConfig,
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
    while attempts < config.max_poll_attempts:
        time.sleep(config.poll_interval_seconds)
        attempts += 1

        current = client.responses.retrieve(response.id)
        status = coerce_optional_string(get_field(current, "status"))

        if status == "completed":
            emit_progress(
                config,
                phase="deep_research",
                status="completed",
                message="Deep research run finished; decoding payload.",
                metadata={"status": status},
            )
            break

        if status in {"failed", "error"}:
            raise DeepResearchError(
                f"Deep research run failed with status: {status}"
            )

        emit_progress(
            config,
            phase="deep_research",
            status="update",
            message="Deep research still running; awaiting updated status.",
            metadata={
                "status": status,
                "poll_attempt": attempts,
            },
        )
    else:
        raise DeepResearchError(
            "Deep research did not complete within the polling limit."
        )

    return current
