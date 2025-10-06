from __future__ import annotations

from typing import Any
import json

from ..config import ResearchConfig
from ..progress import emit_progress
from ..trace import summaries_from_trace_events, trace_event_from_item
from ..utils import (
    coerce_optional_string,
    first_non_empty,
    get_field,
)


__all__ = [
    "accumulate_stream_tool_event",
    "collect_stream_fragments",
    "emit_trace_updates_from_item",
    "extract_stream_error_message",
    "extract_stream_tool_fragment",
    "merge_action_payload",
    "merge_response_payload",
    "merge_tool_fragment",
]


def _coerce_action_payload(payload: Any) -> dict[str, Any]:
    """Normalise tool arguments into a mapping suitable for summaries."""

    if isinstance(payload, dict):
        return payload

    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {"input": payload}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}

    if payload is None:
        return {}

    if isinstance(payload, (list, tuple, set)):
        return {"items": [item for item in payload]}

    return {"value": payload}


def normalize_tool_fragment(fragment: Any) -> dict[str, Any] | None:
    """Coerce streaming tool fragments into the tool-call snapshot format."""

    if not isinstance(fragment, dict):
        return None

    candidate = dict(fragment)

    embedded = candidate.pop("tool_call", None)
    if isinstance(embedded, dict):
        candidate = {**embedded, **candidate}

    # Promote common identifier fields for streaming events.
    identifier = first_non_empty(
        coerce_optional_string(candidate.get(key))
        for key in ("id", "tool_call_id", "call_id")
    )
    if identifier:
        candidate["id"] = identifier

    raw_type = coerce_optional_string(candidate.get("type"))
    tool_name = coerce_optional_string(candidate.get("tool_name"))
    tool_type = coerce_optional_string(candidate.get("tool_type"))

    normalized_type: str | None = None
    if raw_type and raw_type.endswith("_call"):
        normalized_type = raw_type
    elif tool_name:
        normalized_type = f"{tool_name.replace('.', '_')}_call"
    elif tool_type:
        normalized_type = f"{tool_type.replace('.', '_')}_call"
    elif raw_type and raw_type.endswith("_delta"):
        normalized_type = f"{raw_type[: -len('_delta')]}_call"

    if normalized_type:
        candidate["type"] = normalized_type

    status = first_non_empty(
        coerce_optional_string(candidate.get(key))
        for key in ("status", "state")
    )
    if status:
        candidate["status"] = status

    if "arguments" in candidate and "action" not in candidate:
        candidate["action"] = _coerce_action_payload(
            candidate.pop("arguments")
        )

    if "call_arguments" in candidate and "action" not in candidate:
        candidate["action"] = _coerce_action_payload(
            candidate.pop("call_arguments")
        )

    if "input" in candidate and "action" not in candidate:
        candidate["action"] = _coerce_action_payload(candidate.pop("input"))

    if not coerce_optional_string(candidate.get("type")):
        return None

    return candidate


def emit_trace_updates_from_item(
    item: Any,
    *,
    config: ResearchConfig,
    seen_tokens: set[str],
    stream_state: dict[str, Any] | None = None,
) -> None:
    """Convert a tool event into trace summaries and emit them."""
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
    """Merge incremental fragments for a single tool call while streaming."""
    fragments = collect_stream_fragments(item)
    event_id = first_non_empty(
        first_non_empty(
            coerce_optional_string(fragment.get(key))
            for key in ("id", "tool_call_id", "call_id")
        )
        for fragment in fragments
        if isinstance(fragment, dict)
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
        normalized_fragment = normalize_tool_fragment(fragment)
        if normalized_fragment is not None:
            return normalized_fragment

        if (
            isinstance(fragment, dict)
            and (
                fragment.get("response") is not None
                or fragment.get("result") is not None
            )
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
            normalized_snapshot = normalize_tool_fragment(snapshot)
            return normalized_snapshot or snapshot

    return None


def merge_tool_fragment(
    existing: dict[str, Any],
    fragment: dict[str, Any],
) -> dict[str, Any]:
    normalized_existing = normalize_tool_fragment(existing) or existing
    normalized_fragment = normalize_tool_fragment(fragment) or fragment

    merged = dict(normalized_existing)

    if normalized_fragment.get("type"):
        merged["type"] = normalized_fragment["type"]
    if normalized_fragment.get("id"):
        merged["id"] = normalized_fragment["id"]
    if normalized_fragment.get("status"):
        merged["status"] = normalized_fragment["status"]

    action_fragment = normalized_fragment.get("action")
    if action_fragment is not None:
        merged_action = merged.get("action", {})
        merged_action = merge_action_payload(merged_action, action_fragment)
        merged["action"] = merged_action

    if normalized_fragment.get("response") is not None:
        merged["response"] = merge_response_payload(
            merged.get("response"),
            normalized_fragment["response"],
        )

    if normalized_fragment.get("result") is not None:
        merged["result"] = merge_response_payload(
            merged.get("result"),
            normalized_fragment["result"],
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
