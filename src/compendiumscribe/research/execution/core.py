from __future__ import annotations

from typing import Any

from ..config import ResearchConfig
from ..errors import DeepResearchError
from ..progress import emit_progress
from ..utils import coerce_optional_string, get_field
from .polling import await_completion


__all__ = ["execute_deep_research"]


def execute_deep_research(
    client: Any,
    prompt: Any,
    config: ResearchConfig,
):
    """Submit a deep research request and return the completed response."""
    tools: list[dict[str, Any]] = []
    if config.use_web_search:
        tools.append({"type": "web_search_preview"})
    if config.enable_code_interpreter:
        tools.append(
            {"type": "code_interpreter", "container": {"type": "auto"}}
        )

    if not tools:
        raise DeepResearchError(
            "Deep research requires enabling web search or code interpreter."
        )

    request_payload: dict[str, Any] = {
        "model": config.deep_research_model,
        "input": prompt,
        "background": config.background,
        "tools": tools,
    }

    if config.max_tool_calls is not None:
        request_payload["max_tool_calls"] = config.max_tool_calls

    emit_progress(
        config,
        phase="deep_research",
        status="starting",
        message="Submitting deep research request to OpenAI.",
    )

    response = client.responses.create(**request_payload)

    status = (
        coerce_optional_string(get_field(response, "status"))
        or "completed"
    )
    if status in {"in_progress", "queued"}:
        response = await_completion(client, response, config)
    else:
        emit_progress(
            config,
            phase="deep_research",
            status="completed",
            message="Deep research completed synchronously.",
            metadata={"status": status},
        )

    final_status = (
        coerce_optional_string(get_field(response, "status"))
        or "completed"
    )
    if final_status != "completed":
        raise DeepResearchError(
            f"Deep research did not complete successfully: {final_status}"
        )

    return response
