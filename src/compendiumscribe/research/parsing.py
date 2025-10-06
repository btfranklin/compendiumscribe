from __future__ import annotations

from typing import Any
import json

from .errors import DeepResearchError
from .trace import trace_event_from_item
from .utils import coerce_optional_string, get_field


def parse_deep_research_response(response: Any) -> dict[str, Any]:
    text_payload = collect_response_text(response)
    return decode_json_payload(text_payload)


def collect_response_text(response: Any) -> str:
    output_text = get_field(response, "output_text")
    if output_text:
        return str(output_text).strip()

    output_items = get_field(response, "output")
    text_parts: list[str] = []

    if output_items:
        for item in output_items:
            item_type = coerce_optional_string(get_field(item, "type"))
            if item_type == "message":
                for content in get_field(item, "content") or []:
                    text_value = coerce_optional_string(
                        get_field(content, "text")
                    )
                    if not text_value:
                        text_value = coerce_optional_string(
                            get_field(content, "value")
                        )
                    if text_value:
                        text_parts.append(text_value)
            elif item_type == "output_text":
                text = coerce_optional_string(get_field(item, "text"))
                if text:
                    text_parts.append(text)

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
