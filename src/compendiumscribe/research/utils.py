from __future__ import annotations

from typing import Any, Iterable


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


__all__ = [
    "coerce_optional_string",
    "first_non_empty",
    "get_field",
    "stringify_metadata_value",
    "truncate_text",
]
