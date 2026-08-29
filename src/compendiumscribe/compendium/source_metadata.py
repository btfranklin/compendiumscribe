from __future__ import annotations

from datetime import datetime


def normalize_revision(value: str | None) -> str | None:
    """Validate and normalize an optional source revision."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Source revision must be a non-empty string.")
    return value.strip()


def normalize_accessed_at(value: str | None) -> str | None:
    """Validate and normalize an optional source access time."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "Source accessed_at must be a timezone-aware ISO 8601 timestamp."
        )
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            "Source accessed_at must be a timezone-aware ISO 8601 timestamp."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            "Source accessed_at must be a timezone-aware ISO 8601 timestamp."
        )
    return normalized


__all__ = ["normalize_accessed_at", "normalize_revision"]
