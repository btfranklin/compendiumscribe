from __future__ import annotations

from typing import Any, Iterable
import json

from .utils import (
    coerce_optional_string,
    get_field,
    normalize_response_snapshot,
    simplify_action_snapshot,
    truncate_text,
)


def trace_event_from_item(item: Any) -> dict[str, Any] | None:
    item_type = coerce_optional_string(get_field(item, "type")) or ""
    if not item_type.endswith("_call"):
        return None

    event_id = coerce_optional_string(get_field(item, "id"))
    status = coerce_optional_string(get_field(item, "status"))
    action_snapshot = simplify_action_snapshot(get_field(item, "action"))
    response_snapshot = normalize_response_snapshot(
        get_field(item, "response") or get_field(item, "result")
    )

    return {
        "id": event_id,
        "type": item_type,
        "status": status,
        "action": action_snapshot,
        "response": response_snapshot,
    }


def summarize_trace_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", "")).strip() or "tool_call"
    status = str(event.get("status", "")).strip()
    action = event.get("action") or {}

    action_type = str(action.get("type", "")).strip()
    action_name = action_type or str(action.get("name", "")).strip()

    label = action_name or event_type
    summary = label
    if status:
        summary = f"{summary} [{status}]"

    detail = None
    for key in ("query", "input", "instructions", "code", "prompt"):
        value = action.get(key)
        if isinstance(value, str) and value.strip():
            detail = truncate_text(value)
            break

    if detail:
        summary = f"{summary}: {detail}"

    return summary


def summaries_from_trace_events(
    events: Iterable[dict[str, Any]],
    seen_tokens: set[str],
) -> list[dict[str, Any]]:
    search_queries: list[str] = []
    open_pages = 0
    find_in_page = 0
    code_runs = 0
    fallbacks: list[dict[str, Any]] = []

    for event in events:
        token = trace_event_token(event)
        if token in seen_tokens:
            continue
        seen_tokens.add(token)

        action = event.get("action") or {}
        action_type = str(action.get("type", "")).lower()
        query = coerce_optional_string(action.get("query"))
        event_type = str(event.get("type", "")).lower()

        if event_type.endswith("web_search_call") or action_type == "search":
            if query:
                search_queries.append(query)
            else:
                fallbacks.append(event)
            continue

        if "open_page" in event_type:
            open_pages += 1
            continue

        if "find_in_page" in event_type or action_type == "find":
            find_in_page += 1
            continue

        if event_type.endswith("code_interpreter_call") or action_type in (
            "code",
            "python",
        ):
            code_runs += 1
            continue

        fallback_message = summarize_trace_event(event)
        fallbacks.append(
            {
                "status": "update",
                "message": fallback_message,
                "metadata": {
                    "type": event.get("type"),
                    "status": event.get("status"),
                    "id": event.get("id"),
                },
            }
        )

    summaries: list[dict[str, Any]] = []

    if search_queries:
        summaries.append(
            {
                "status": "update",
                "message": (
                    "Exploring sources for "
                    f"{format_query_list(search_queries)}"
                ),
                "metadata": {
                    "kind": "web_search",
                    "queries": search_queries,
                },
            }
        )

    if open_pages:
        summaries.append(
            {
                "status": "update",
                "message": (
                    f"Reviewing {open_pages} opened reference"
                    f"{'s' if open_pages != 1 else ''}."
                ),
                "metadata": {
                    "kind": "open_page",
                    "count": open_pages,
                },
            }
        )

    if find_in_page:
        summaries.append(
            {
                "status": "update",
                "message": (
                    "Scanning within sources for targeted evidence "
                    f"({find_in_page} find-in-page call"
                    f"{'s' if find_in_page != 1 else ''})."
                ),
                "metadata": {
                    "kind": "find_in_page",
                    "count": find_in_page,
                },
            }
        )

    if code_runs:
        summaries.append(
            {
                "status": "update",
                "message": (
                    f"Running {code_runs} code interpreter action"
                    f"{'s' if code_runs != 1 else ''}."
                ),
                "metadata": {
                    "kind": "code_interpreter",
                    "count": code_runs,
                },
            }
        )

    summaries.extend(fallbacks)
    return summaries


def format_query_list(queries: list[str], limit: int = 3) -> str:
    unique_queries: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = query.strip()
        if not normalized:
            continue
        fingerprint = normalized.lower()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique_queries.append(normalized)

    if not unique_queries:
        return "current search focus"

    display = [f'"{item}"' for item in unique_queries[:limit]]
    if len(unique_queries) > limit:
        display.append(f"(+{len(unique_queries) - limit} more)")
    return ", ".join(display)


def trace_event_token(event: dict[str, Any]) -> str:
    event_id = event.get("id")
    if event_id:
        token_parts = ["id", str(event_id)]
        status = coerce_optional_string(event.get("status"))
        if status:
            token_parts.extend(["status", status])
        action = event.get("action") or {}
        if isinstance(action, dict):
            query = coerce_optional_string(action.get("query"))
            if query:
                token_parts.extend(["query", query])
        return ":".join(token_parts)

    action = event.get("action") or {}
    query = coerce_optional_string(action.get("query"))
    if query:
        return f"search:{query.lower()}"

    action_name = coerce_optional_string(action.get("name"))
    if action_name:
        return f"action:{action_name.lower()}"

    event_type = coerce_optional_string(event.get("type")) or "generic"
    action_repr = json.dumps(action, sort_keys=True, default=str)
    return f"{event_type}:{action_repr}"


def iter_trace_progress_events(response: Any) -> Iterable[dict[str, Any]]:
    output_items = getattr(response, "output", None)
    if not output_items:
        return []

    events: list[dict[str, Any]] = []
    for item in output_items:
        item_type = coerce_optional_string(get_field(item, "type"))
        if not item_type or not item_type.endswith("_call"):
            continue

        event_id = coerce_optional_string(get_field(item, "id"))
        status = coerce_optional_string(get_field(item, "status"))
        action_snapshot = simplify_action_snapshot(
            get_field(item, "action")
        )

        events.append(
            {
                "id": event_id,
                "type": item_type,
                "status": status or "update",
                "action": action_snapshot,
            }
        )

    return events


__all__ = [
    "format_query_list",
    "iter_trace_progress_events",
    "summaries_from_trace_events",
    "summarize_trace_event",
    "trace_event_from_item",
    "trace_event_token",
]
