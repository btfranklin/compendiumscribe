from __future__ import annotations

from typing import Any
import json
import time

from .config import ResearchConfig
from .errors import DeepResearchError
from .progress import emit_progress
from .trace import (
    iter_trace_progress_events,
    summaries_from_trace_events,
    trace_event_from_item,
)
from .utils import (
    coerce_optional_string,
    first_non_empty,
    get_field,
)


def execute_deep_research(
    client: Any,
    prompt: str,
    config: ResearchConfig,
):
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

    if config.stream_progress:
        return execute_deep_research_streaming(
            client,
            request_payload,
            config,
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


def await_completion(
    client: Any,
    response: Any,
    config: ResearchConfig,
):
    attempts = 0
    seen_tokens: set[str] = set()

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

        current = client.responses.get(response.id)
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

        trace = summaries_from_trace_events(
            iter_trace_progress_events(current),
            seen_tokens,
        )
        for summary in trace:
            emit_progress(
                config,
                phase="trace",
                status=summary["status"],
                message=summary["message"],
                metadata=summary["metadata"],
            )

        emit_progress(
            config,
            phase="deep_research",
            status="update",
            message=(
                "Deep research still running; awaiting updated status "
                f"(poll #{attempts})."
            ),
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


def execute_deep_research_streaming(
    client: Any,
    request_payload: dict[str, Any],
    config: ResearchConfig,
):
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


def emit_trace_updates_from_item(
    item: Any,
    *,
    config: ResearchConfig,
    seen_tokens: set[str],
    stream_state: dict[str, Any] | None = None,
) -> None:
    if stream_state is not None:
        event_snapshot = accumulate_stream_tool_event(item, stream_state)
    else:
        event_snapshot = trace_event_from_item(item)
    if not event_snapshot:
        return

    summaries = summaries_from_trace_events([event_snapshot], seen_tokens)
    for summary in summaries:
        emit_progress(
            config,
            phase="trace",
            status=summary.get("status", "update"),
            message=summary["message"],
            metadata=summary.get("metadata"),
        )


def accumulate_stream_tool_event(
    item: Any,
    stream_state: dict[str, Any],
) -> dict[str, Any] | None:
    fragments = collect_stream_fragments(item)
    event_id = first_non_empty(
        coerce_optional_string(fragment.get("id"))
        for fragment in fragments
    )

    tool_events: dict[str, dict[str, Any]] = stream_state.setdefault(
        "tool_events", {}
    )
    existing = tool_events.get(event_id or "", {}) if event_id else {}

    fragment = extract_stream_tool_fragment(fragments, existing)
    if fragment is None:
        return None

    merged = merge_tool_fragment(existing, fragment)
    if event_id:
        tool_events[event_id] = merged

    return trace_event_from_item(merged)


def collect_stream_fragments(item: Any) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []

    def maybe_append(candidate: Any) -> None:
        if isinstance(candidate, dict):
            fragments.append(candidate)

    maybe_append(item)
    maybe_append(get_field(item, "item"))
    maybe_append(get_field(item, "delta"))

    return fragments


def extract_stream_tool_fragment(
    fragments: list[dict[str, Any]],
    existing: dict[str, Any],
) -> dict[str, Any] | None:
    for fragment in fragments:
        item_type = coerce_optional_string(fragment.get("type"))
        if item_type and item_type.endswith("_call"):
            return fragment

        if (
            fragment.get("response") is not None
            or fragment.get("result") is not None
        ):
            snapshot = dict(existing)
            if fragment.get("response") is not None:
                snapshot.setdefault("response", {}).update(
                    fragment.get("response") or {}
                )
            if fragment.get("result") is not None:
                snapshot.setdefault("result", {}).update(
                    fragment.get("result") or {}
                )
            return snapshot

    return None


def merge_tool_fragment(
    existing: dict[str, Any],
    fragment: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing)

    if fragment.get("type"):
        merged["type"] = fragment["type"]
    if fragment.get("id"):
        merged["id"] = fragment["id"]
    if fragment.get("status"):
        merged["status"] = fragment["status"]

    action_fragment = fragment.get("action")
    if action_fragment is not None:
        merged_action = merged.get("action", {})
        merged_action = merge_action_payload(merged_action, action_fragment)
        merged["action"] = merged_action

    if fragment.get("response") is not None:
        merged["response"] = merge_response_payload(
            merged.get("response"),
            fragment["response"],
        )

    if fragment.get("result") is not None:
        merged["result"] = merge_response_payload(
            merged.get("result"),
            fragment["result"],
        )

    return merged


def merge_action_payload(
    existing: Any,
    incoming: Any,
) -> Any:
    if not isinstance(incoming, dict):
        return incoming

    existing_dict = dict(existing) if isinstance(existing, dict) else {}

    for key, value in incoming.items():
        if key.endswith("_delta") and isinstance(value, str):
            base_key = key[: -len("_delta")]
            existing_value = coerce_optional_string(
                existing_dict.get(base_key)
            )
            existing_dict[base_key] = (existing_value or "") + value
            continue

        if isinstance(value, dict):
            nested_existing = existing_dict.get(key)
            nested_merged = merge_action_payload(nested_existing, value)
            existing_dict[key] = nested_merged
            continue

        existing_dict[key] = value

    return existing_dict


def merge_response_payload(
    existing: Any,
    incoming: Any,
) -> Any:
    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = dict(existing)
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = merge_response_payload(merged[key], value)
            else:
                merged[key] = value
        return merged

    return incoming if incoming is not None else existing


def extract_stream_error_message(event: Any) -> str:
    error = get_field(event, "error")
    if error is None:
        message = get_field(event, "message")
        return coerce_optional_string(message) or "unknown error"

    if isinstance(error, dict):
        message = coerce_optional_string(error.get("message"))
        if message:
            return message
        code = coerce_optional_string(error.get("code"))
        if code:
            return code
        return json.dumps(error, default=str)

    return coerce_optional_string(error) or "unknown error"


__all__ = [
    "accumulate_stream_tool_event",
    "await_completion",
    "collect_stream_fragments",
    "execute_deep_research",
    "execute_deep_research_streaming",
    "emit_trace_updates_from_item",
    "extract_stream_error_message",
    "extract_stream_tool_fragment",
    "handle_stream_event",
    "merge_action_payload",
    "merge_response_payload",
    "merge_tool_fragment",
]
