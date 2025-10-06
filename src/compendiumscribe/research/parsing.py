from __future__ import annotations

from typing import Any
import json

from .errors import DeepResearchError
from .trace import trace_event_from_item
from .utils import coerce_optional_string, get_field


def _iter_text_fragments(value: Any) -> list[str]:
    """Recursively extract textual fragments from nested response payloads."""

    fragments: list[str] = []

    def visit(candidate: Any) -> None:
        if candidate is None:
            return

        if isinstance(candidate, str):
            if candidate:
                fragments.append(candidate)
            return

        if isinstance(candidate, (list, tuple, set)):
            for item in candidate:
                visit(item)
            return

        if isinstance(candidate, dict):
            # Many response payloads nest text inside these keys.
            for key in ("text", "value", "content"):
                if key in candidate:
                    visit(candidate[key])
            return

        # Safety fallback: stringify scalars only (avoid object reprs).
        if isinstance(candidate, (int, float, bool)):
            fragments.append(str(candidate))

    visit(value)
    return fragments


def parse_deep_research_response(response: Any) -> dict[str, Any]:
    text_payload = collect_response_text(response)
    return decode_json_payload(text_payload)


def collect_response_text(response: Any) -> str:
    output_text = get_field(response, "output_text")
    if output_text:
        fragments = _iter_text_fragments(output_text)
        if fragments:
            return "".join(fragments).strip()

    output_items = get_field(response, "output")
    text_parts: list[str] = []

    if output_items:
        for item in output_items:
            item_type = coerce_optional_string(get_field(item, "type"))
            if item_type == "message":
                for content in get_field(item, "content") or []:
                    fragments = _iter_text_fragments(content)
                    if fragments:
                        text_parts.append("".join(fragments))
            elif item_type == "output_text":
                fragments = _iter_text_fragments(item)
                if fragments:
                    text_parts.append("".join(fragments))

    if text_parts:
        return "".join(text_parts).strip()

    raise DeepResearchError(
        "Deep research response did not include textual output."
    )


def decode_json_payload(text: str) -> dict[str, Any]:
    candidate = text.strip()

    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()

    if candidate and not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1:
            raise DeepResearchError(
                "Unable to locate JSON object in response."
            )
        candidate = candidate[start:end + 1]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DeepResearchError(
            "Deep research response was not valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise DeepResearchError(
            "Expected JSON object at top level of response."
        )

    return payload


def extract_trace_events(response: Any) -> list[dict[str, Any]]:
    output_items = get_field(response, "output")
    trace: list[dict[str, Any]] = []

    if not output_items:
        return trace

    for item in output_items:
        event_snapshot = trace_event_from_item(item)
        if event_snapshot:
            trace.append(event_snapshot)

    return trace


__all__ = [
    "collect_response_text",
    "decode_json_payload",
    "extract_trace_events",
    "parse_deep_research_response",
]
