from __future__ import annotations

from typing import Any, Iterable

ACTION_SUMMARY_KEYS = (
    "type",
    "name",
    "query",
    "input",
    "instructions",
    "code",
    "prompt",
)


def first_non_empty(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def truncate_text(value: str, max_length: int = 120) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"


def get_field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def coerce_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def stringify_metadata_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            key: stringify_metadata_value(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [stringify_metadata_value(item) for item in value]
    return str(value)


def simplify_action_snapshot(action: Any) -> dict[str, Any]:
    if not action:
        return {}

    if isinstance(action, dict):
        snapshot: dict[str, Any] = {}
        for key in ACTION_SUMMARY_KEYS:
            value = action.get(key)
            if value not in (None, ""):
                snapshot[key] = stringify_metadata_value(value)
        return snapshot

    snapshot = {}
    for key in ACTION_SUMMARY_KEYS:
        value = getattr(action, key, None)
        if value not in (None, ""):
            snapshot[key] = stringify_metadata_value(value)
    return snapshot


def normalize_response_snapshot(response: Any) -> Any:
    if response is None:
        return None
    if isinstance(response, (str, int, float, bool)):
        return response
    if isinstance(response, dict):
        return {
            key: stringify_metadata_value(value)
            for key, value in response.items()
        }
    if isinstance(response, list):
        return [stringify_metadata_value(item) for item in response]
    return stringify_metadata_value(response)


__all__ = [
    "ACTION_SUMMARY_KEYS",
    "coerce_optional_string",
    "first_non_empty",
    "get_field",
    "normalize_response_snapshot",
    "simplify_action_snapshot",
    "stringify_metadata_value",
    "truncate_text",
]
