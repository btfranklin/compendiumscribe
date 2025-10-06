from __future__ import annotations

from typing import Any

from ..config import ResearchConfig
from ..errors import DeepResearchError
from ..progress import emit_progress
from ..utils import coerce_optional_string, get_field
from .stream_events import (
    emit_trace_updates_from_item,
    extract_stream_error_message,
)


__all__ = [
    "execute_deep_research_streaming",
    "handle_stream_event",
]


def execute_deep_research_streaming(
    client: Any,
    request_payload: dict[str, Any],
    config: ResearchConfig,
):
    """Stream deep research events until a final response is available."""
    payload = dict(request_payload)

    if payload.get("background"):
        payload["background"] = False
        emit_progress(
            config,
            phase="deep_research",
            status="update",
            message=(
                "Streaming requires synchronous execution; disabling "
                "background mode."
            ),
        )

    payload["stream"] = True

    try:
        stream = client.responses.create(**payload)
    except TypeError as exc:
        raise RuntimeError(
            "OpenAI client does not support streaming responses; "
            "upgrade the SDK to a version that implements the Responses "
            "streaming protocol."
        ) from exc

    seen_trace_tokens: set[str] = set()
    stream_state: dict[str, Any] = {"status_events": set()}
    final_response: Any | None = None

    emit_progress(
        config,
        phase="deep_research",
        status="in_progress",
        message="Streaming deep research events from OpenAI.",
    )

    for event in stream:
        response_candidate = handle_stream_event(
            event,
            config=config,
            seen_trace_tokens=seen_trace_tokens,
            stream_state=stream_state,
        )
        if response_candidate is not None:
            final_response = response_candidate

    if final_response is None and hasattr(stream, "get_final_response"):
        final_response = stream.get_final_response()

    if final_response is None:
        raise DeepResearchError(
            "Deep research stream completed without a final response."
        )

    final_status = (
        coerce_optional_string(get_field(final_response, "status"))
        or "completed"
    )
    if final_status != "completed":
        raise DeepResearchError(
            f"Deep research did not complete successfully: {final_status}"
        )

    emit_progress(
        config,
        phase="deep_research",
        status="completed",
        message="Deep research stream finished; decoding payload.",
        metadata={"status": final_status},
    )

    return final_response


def handle_stream_event(
    event: Any,
    *,
    config: ResearchConfig,
    seen_trace_tokens: set[str],
    stream_state: dict[str, Any],
) -> Any | None:
    """Process a streaming event and return a completed response when ready."""
    event_type = coerce_optional_string(get_field(event, "type"))
    if not event_type:
        return None

    normalized = event_type.lower()

    if normalized in {"response.created", "response.in_progress"}:
        status_events = stream_state.setdefault("status_events", set())
        if normalized not in status_events:
            status_events.add(normalized)
            status = (
                "starting"
                if normalized == "response.created"
                else "in_progress"
            )
            emit_progress(
                config,
                phase="deep_research",
                status=status,
                message=f"Deep research status event: {event_type}.",
            )
        return None

    if normalized in {"response.failed", "response.error", "error"}:
        message = extract_stream_error_message(event) or event_type
        raise DeepResearchError(
            f"Deep research stream reported an error: {message}"
        )

    if "tool_call" in normalized:
        fragment = (
            get_field(event, "item")
            or get_field(event, "delta")
            or get_field(event, "partial")
            or get_field(event, "data")
        )
        if fragment is not None:
            emit_trace_updates_from_item(
                fragment,
                config=config,
                seen_tokens=seen_trace_tokens,
                stream_state=stream_state,
            )
        return None

    if normalized == "response.output_item.added":
        item = get_field(event, "item")
        if item is not None:
            emit_trace_updates_from_item(
                item,
                config=config,
                seen_tokens=seen_trace_tokens,
                stream_state=stream_state,
            )
        return None

    if normalized == "response.output_item.delta":
        delta = get_field(event, "delta")
        if delta is not None:
            emit_trace_updates_from_item(
                delta,
                config=config,
                seen_tokens=seen_trace_tokens,
                stream_state=stream_state,
            )
        return None

    if normalized in {
        "response.output_text.delta",
        "response.output_text.done",
        "response.output_text.added",
        "response.content_part.added",
        "response.content_part.delta",
    }:
        return None

    if normalized == "response.completed":
        response_obj = get_field(event, "response")
        if response_obj is not None:
            return response_obj
        return None

    return None
