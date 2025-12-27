from __future__ import annotations

from typing import Any
import json

from .errors import DeepResearchError
from .utils import coerce_optional_string, get_field


def _iter_text_fragments(value: Any) -> list[str]:
    """Recursively extract textual fragments from nested response payloads.

    This is necessary because the Responses API can return text nested in
    various structures (e.g. within "message" or "output_text" items).
    """

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
            # Known keys where text content is typically stored.
            for key in ("text", "value", "content"):
                if (val := candidate.get(key)) is not None:
                    visit(val)
            return

        # Safety fallback: stringify basic scalars only.
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

    # Helper to create a preview snippet for error messages
    def _snippet(s: str, max_len: int = 200) -> str:
        if len(s) <= max_len:
            return s
        return s[:max_len] + "..."

    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()

    if candidate and not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1:
            raise DeepResearchError(
                f"Unable to locate JSON object in response. "
                f"Received: {_snippet(text)!r}"
            )
        candidate = candidate[start:end + 1]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DeepResearchError(
            f"Deep research response was not valid JSON. "
            f"Parse error at position {exc.pos}: {exc.msg}. "
            f"Content: {_snippet(candidate)!r}"
        ) from exc

    if not isinstance(payload, dict):
        raise DeepResearchError(
            f"Expected JSON object at top level of response, "
            f"got {type(payload).__name__}: {_snippet(str(payload))!r}"
        )

    return payload


__all__ = [
    "collect_response_text",
    "decode_json_payload",
    "parse_deep_research_response",
]
