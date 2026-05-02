from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re

from compendiumscribe.compendium import Compendium, Section, slugify

from .models import (
    Catalog,
    CatalogEntry,
    CardSection,
    CompendiumCard,
)


CATALOG_FILENAME = "catalog.json"
COMPENDIUMS_DIR = "compendiums"
COMPENDIUM_XML_FILENAME = "compendium.xml"
COMPENDIUM_MARKDOWN_FILENAME = "compendium.md"
CARD_FILENAME = "card.json"
MAX_CATALOG_SUMMARY_CHARS = 500
MAX_SECTION_SUMMARY_CHARS = 280
MAX_KEYWORDS = 14

_STOP_WORDS = {
    "about",
    "after",
    "agent",
    "agents",
    "and",
    "are",
    "best",
    "can",
    "for",
    "from",
    "has",
    "how",
    "into",
    "its",
    "methodologies",
    "methodology",
    "practices",
    "production",
    "that",
    "the",
    "their",
    "this",
    "through",
    "with",
}


class LibraryError(RuntimeError):
    """Raised when library persistence fails."""


def load_catalog(library_path: Path) -> Catalog:
    """Load a library catalog, returning an empty catalog for new libraries."""

    catalog_path = library_path / CATALOG_FILENAME
    if not catalog_path.exists():
        return Catalog(updated_at=_utc_now())

    try:
        return Catalog.model_validate_json(
            catalog_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise LibraryError(f"Failed to parse {catalog_path}: {exc}") from exc


def publish_compendium(
    compendium: Compendium,
    library_path: Path,
) -> CatalogEntry:
    """Publish or update a compendium in a filesystem-backed library."""

    library_path = library_path.expanduser()
    library_path.mkdir(parents=True, exist_ok=True)
    (library_path / COMPENDIUMS_DIR).mkdir(parents=True, exist_ok=True)

    catalog = load_catalog(library_path)
    now = _utc_now()
    title = compendium.topic.strip() or "Untitled Compendium"
    entry_id = _choose_entry_id(catalog, slugify(title), title)
    existing_entry = _entry_by_id(catalog, entry_id)
    created_at = existing_entry.created_at if existing_entry else now

    compendium_dir = library_path / COMPENDIUMS_DIR / entry_id
    compendium_dir.mkdir(parents=True, exist_ok=True)

    xml_path = _relative_path(
        COMPENDIUMS_DIR,
        entry_id,
        COMPENDIUM_XML_FILENAME,
    )
    markdown_path = _relative_path(
        COMPENDIUMS_DIR,
        entry_id,
        COMPENDIUM_MARKDOWN_FILENAME,
    )
    card_path = _relative_path(COMPENDIUMS_DIR, entry_id, CARD_FILENAME)

    summary = _truncate_text(
        getattr(compendium, "overview", ""),
        max_chars=MAX_CATALOG_SUMMARY_CHARS,
    )
    keywords = derive_keywords(compendium)
    entry = CatalogEntry(
        id=entry_id,
        title=title,
        summary=summary,
        keywords=keywords,
        path=xml_path,
        markdown_path=markdown_path,
        card_path=card_path,
        created_at=created_at,
        updated_at=now,
    )
    card = build_card(
        compendium,
        entry_id=entry_id,
        created_at=created_at,
        updated_at=now,
        xml_path=xml_path,
        markdown_path=markdown_path,
    )

    (library_path / xml_path).write_text(
        compendium.to_xml_string(),
        encoding="utf-8",
    )
    (library_path / markdown_path).write_text(
        compendium.to_markdown(),
        encoding="utf-8",
    )
    _write_json(library_path / card_path, card)

    _upsert_entry(catalog, entry)
    catalog.updated_at = now
    _write_json(library_path / CATALOG_FILENAME, catalog)
    return entry


def import_compendium_xml(
    *,
    library_path: Path,
    compendium_xml: Path,
) -> CatalogEntry:
    """Import an existing XML compendium into a library."""

    try:
        compendium = Compendium.from_xml_file(str(compendium_xml))
    except Exception as exc:
        raise LibraryError(
            f"Failed to parse compendium XML {compendium_xml}: {exc}"
        ) from exc
    return publish_compendium(compendium, library_path)


def build_card(
    compendium: Compendium,
    *,
    entry_id: str,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    xml_path: str | None = None,
    markdown_path: str | None = None,
) -> CompendiumCard:
    """Build the progressive-disclosure metadata card for a compendium."""

    now = _utc_now()
    created_at = created_at or now
    updated_at = updated_at or now
    sections = list(getattr(compendium, "sections", []) or [])
    citations = list(getattr(compendium, "citations", []) or [])
    return CompendiumCard(
        id=entry_id,
        title=(getattr(compendium, "topic", "") or "Untitled Compendium"),
        summary=_truncate_text(
            getattr(compendium, "overview", ""),
            max_chars=MAX_CATALOG_SUMMARY_CHARS,
        ),
        sections=[
            CardSection(
                id=section.identifier,
                title=section.title,
                summary=_truncate_text(
                    section.summary,
                    max_chars=MAX_SECTION_SUMMARY_CHARS,
                ),
            )
            for section in sections
        ],
        keywords=derive_keywords(compendium),
        section_count=len(sections),
        citation_count=len(citations),
        source_count=len(citations),
        path=xml_path
        or _relative_path(
            COMPENDIUMS_DIR,
            entry_id,
            COMPENDIUM_XML_FILENAME,
        ),
        markdown_path=markdown_path
        or _relative_path(
            COMPENDIUMS_DIR,
            entry_id,
            COMPENDIUM_MARKDOWN_FILENAME,
        ),
        created_at=created_at,
        updated_at=updated_at,
    )


def derive_keywords(compendium: Compendium) -> list[str]:
    """Derive compact, deterministic keywords without using an LLM."""

    candidates: list[str] = []
    candidates.extend(_tokenize(getattr(compendium, "topic", "")))
    for section in _iter_sections(compendium):
        candidates.extend(_tokenize(section.title))
        candidates.extend(_normalize_keyword(term) for term in section.key_terms)

    keywords: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in _STOP_WORDS or candidate in seen:
            continue
        seen.add(candidate)
        keywords.append(candidate)
        if len(keywords) >= MAX_KEYWORDS:
            break
    return keywords


def _choose_entry_id(
    catalog: Catalog,
    preferred_id: str,
    title: str,
) -> str:
    entries_by_id = {entry.id: entry for entry in catalog.entries}
    existing = entries_by_id.get(preferred_id)
    if existing is None or _same_title(existing.title, title):
        return preferred_id

    suffix = 2
    while True:
        candidate = f"{preferred_id}-{suffix}"
        existing = entries_by_id.get(candidate)
        if existing is None or _same_title(existing.title, title):
            return candidate
        suffix += 1


def _entry_by_id(catalog: Catalog, entry_id: str) -> CatalogEntry | None:
    return next(
        (entry for entry in catalog.entries if entry.id == entry_id),
        None,
    )


def _upsert_entry(catalog: Catalog, entry: CatalogEntry) -> None:
    catalog.entries = [
        existing for existing in catalog.entries if existing.id != entry.id
    ]
    catalog.entries.append(entry)
    catalog.entries.sort(key=lambda item: (item.title.lower(), item.id))


def _write_json(path: Path, model: Catalog | CompendiumCard) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _relative_path(*parts: str) -> str:
    return str(PurePosixPath(*parts))


def _truncate_text(value: str | None, *, max_chars: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= max_chars:
        return text
    truncated = text[: max_chars - 3].rsplit(" ", 1)[0].rstrip()
    if not truncated:
        truncated = text[: max_chars - 3].rstrip()
    return f"{truncated}..."


def _iter_sections(compendium: Compendium) -> Iterable[Section]:
    return getattr(compendium, "sections", []) or []


def _tokenize(value: str | None) -> list[str]:
    return [
        token
        for token in (
            _normalize_keyword(match.group(0))
            for match in re.finditer(r"[A-Za-z][A-Za-z0-9-]*", value or "")
        )
        if token
    ]


def _normalize_keyword(value: str | None) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip().lower())
    normalized = normalized.strip(".,;:!?()[]{}\"'")
    if len(normalized) < 3:
        return ""
    return normalized


def _same_title(left: str, right: str) -> bool:
    return " ".join(left.lower().split()) == " ".join(right.lower().split())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
