from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import yaml

from compendiumscribe.compendium import Compendium, slugify
from compendiumscribe.compendium.okf import (
    COMPENDIUM_FILENAME,
    INDEX_FILENAME,
    OKFError,
    ValidationIssue,
    parse_concept,
    read_concept,
    render_okf_bundle,
    validate_okf_bundle,
    write_okf_bundle,
)

from .models import LibraryEntry


COMPENDIUMS_DIR = "compendiums"


class LibraryError(RuntimeError):
    """Raised when a Compendium Library operation cannot complete."""


def publish_compendium(
    compendium: Compendium,
    library_path: Path,
) -> LibraryEntry:
    """Publish or replace a Compendium in a strict OKF Library."""

    destination = library_path.expanduser()
    existing_entries = _entries_for_update(destination)
    entry_id = _choose_entry_id(
        existing_entries,
        slugify(compendium.topic),
        compendium.topic,
    )
    files = render_okf_bundle(compendium, compendium_id=entry_id)
    return _commit_entry(
        destination,
        entry_id=entry_id,
        files=files,
    )


def import_compendium(
    *,
    library_path: Path,
    source_path: Path,
) -> LibraryEntry:
    """Import an XML compendium or OKF bundle into a strict OKF Library."""

    source = source_path.expanduser()
    if source.is_dir():
        issues = validate_okf_bundle(source)
        if issues:
            raise LibraryError(
                _issues_message(f"Invalid OKF source {source}", issues)
            )
        source_doc = read_concept(source / COMPENDIUM_FILENAME)
        title = str(source_doc.frontmatter.get("title") or "").strip()
        if not title:
            raise LibraryError(
                f"OKF source {source} has no compendium title."
            )
        destination = library_path.expanduser()
        existing_entries = _entries_for_update(destination)
        entry_id = _choose_entry_id(
            existing_entries,
            slugify(title),
            title,
        )
        files = _read_bundle_files(source)
        files[COMPENDIUM_FILENAME] = _replace_frontmatter_value(
            files[COMPENDIUM_FILENAME],
            "id",
            entry_id,
        )
        return _commit_entry(
            destination,
            entry_id=entry_id,
            files=files,
        )

    if source.is_file() and source.suffix.lower() == ".xml":
        try:
            compendium = Compendium.from_xml_file(str(source))
        except Exception as exc:
            raise LibraryError(
                f"Failed to parse compendium XML {source}: {exc}"
            ) from exc
        return publish_compendium(compendium, library_path)

    raise LibraryError(
        "Compendium source must be an XML file or a CompendiumScribe "
        f"OKF directory: {source}"
    )


def list_library_entries(library_path: Path) -> list[LibraryEntry]:
    """List entries by scanning validated OKF compendium concepts."""

    root = library_path.expanduser()
    issues = validate_library(root)
    if issues:
        raise LibraryError(_issues_message(f"Invalid Library {root}", issues))
    return _scan_entries(root)


def validate_library(
    library_path: Path,
) -> tuple[ValidationIssue, ...]:
    """Validate a strict CompendiumScribe OKF Library."""

    root = library_path.expanduser()
    issues: list[ValidationIssue] = []
    if not root.exists():
        return (
            ValidationIssue(".", "library_missing", "Library does not exist."),
        )
    if not root.is_dir() or root.is_symlink():
        return (
            ValidationIssue(
                ".",
                "library_not_directory",
                "Library root must be a real directory.",
            ),
        )
    expected_root = {INDEX_FILENAME, COMPENDIUMS_DIR}
    for child in root.iterdir():
        relative = child.name
        if child.is_symlink():
            issues.append(
                ValidationIssue(
                    relative,
                    "symlink_forbidden",
                    "Symlinks are not allowed in managed OKF Libraries.",
                )
            )
        elif child.name not in expected_root:
            issues.append(
                ValidationIssue(
                    relative,
                    "unexpected_library_file",
                    "Strict OKF Libraries contain only index.md and "
                    "the compendiums directory.",
                )
            )

    root_index = root / INDEX_FILENAME
    compendiums_path = root / COMPENDIUMS_DIR
    compendiums_index = compendiums_path / INDEX_FILENAME
    if not root_index.is_file():
        issues.append(
            ValidationIssue(
                INDEX_FILENAME,
                "required_file_missing",
                "Library index.md is missing.",
            )
        )
    elif root_index.read_text(encoding="utf-8") != _root_index():
        issues.append(
            ValidationIssue(
                INDEX_FILENAME,
                "library_index_invalid",
                "Library index.md does not match the CompendiumScribe profile.",
            )
        )

    if not compendiums_path.is_dir() or compendiums_path.is_symlink():
        issues.append(
            ValidationIssue(
                COMPENDIUMS_DIR,
                "required_directory_missing",
                "Library compendiums directory is missing.",
            )
        )
        return _deduplicate_issues(issues)
    if not compendiums_index.is_file():
        issues.append(
            ValidationIssue(
                f"{COMPENDIUMS_DIR}/{INDEX_FILENAME}",
                "required_file_missing",
                "Compendium inventory index is missing.",
            )
        )

    entries: list[LibraryEntry] = []
    for child in sorted(compendiums_path.iterdir()):
        if child.name == INDEX_FILENAME:
            continue
        relative_prefix = f"{COMPENDIUMS_DIR}/{child.name}"
        if child.is_symlink():
            issues.append(
                ValidationIssue(
                    relative_prefix,
                    "symlink_forbidden",
                    "Symlinks are not allowed in managed OKF Libraries.",
                )
            )
            continue
        if not child.is_dir():
            issues.append(
                ValidationIssue(
                    relative_prefix,
                    "non_compendium_entry",
                    "Every Library entry must be an OKF compendium directory.",
                )
            )
            continue
        bundle_issues = validate_okf_bundle(child)
        issues.extend(
            ValidationIssue(
                f"{relative_prefix}/{issue.path}",
                issue.code,
                issue.message,
            )
            for issue in bundle_issues
        )
        if bundle_issues:
            continue
        try:
            entry = _entry_from_directory(child, root=root)
        except (OKFError, KeyError, TypeError, ValueError) as exc:
            issues.append(
                ValidationIssue(
                    f"{relative_prefix}/{COMPENDIUM_FILENAME}",
                    "invalid_library_entry",
                    str(exc),
                )
            )
            continue
        if entry.id != child.name:
            issues.append(
                ValidationIssue(
                    f"{relative_prefix}/{COMPENDIUM_FILENAME}",
                    "entry_id_mismatch",
                    "Compendium frontmatter id must match its Library "
                    "directory name.",
                )
            )
        entries.append(entry)

    if compendiums_index.is_file():
        try:
            actual_index = compendiums_index.read_text(encoding="utf-8")
        except UnicodeError:
            issues.append(
                ValidationIssue(
                    f"{COMPENDIUMS_DIR}/{INDEX_FILENAME}",
                    "invalid_utf8",
                    "Library indexes must be UTF-8.",
                )
            )
        else:
            expected_index = _compendiums_index(entries)
            if actual_index != expected_index:
                issues.append(
                    ValidationIssue(
                        f"{COMPENDIUMS_DIR}/{INDEX_FILENAME}",
                        "inventory_index_stale",
                        "Compendium inventory does not match the Library entries.",
                    )
                )
    return _deduplicate_issues(issues)


def _commit_entry(
    library_path: Path,
    *,
    entry_id: str,
    files: Mapping[str, str],
) -> LibraryEntry:
    library_path.parent.mkdir(parents=True, exist_ok=True)
    staging_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{library_path.name}.",
            dir=library_path.parent,
        )
    )
    candidate = staging_parent / library_path.name
    try:
        if library_path.exists():
            shutil.copytree(library_path, candidate)
        else:
            _initialize_library(candidate)

        target = candidate / COMPENDIUMS_DIR / entry_id
        write_okf_bundle(target, files)
        entries = _scan_entries(candidate)
        _atomic_write(
            candidate / COMPENDIUMS_DIR / INDEX_FILENAME,
            _compendiums_index(entries),
        )
        _atomic_write(candidate / INDEX_FILENAME, _root_index())

        issues = validate_library(candidate)
        if issues:
            raise LibraryError(
                _issues_message("Candidate Library is invalid", issues)
            )
        _replace_directory(candidate, library_path, staging_parent)
        return next(entry for entry in entries if entry.id == entry_id)
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)


def _entries_for_update(library_path: Path) -> list[LibraryEntry]:
    if not library_path.exists():
        return []
    issues = validate_library(library_path)
    if issues:
        raise LibraryError(
            _issues_message(f"Invalid Library {library_path}", issues)
        )
    return _scan_entries(library_path)


def _initialize_library(path: Path) -> None:
    (path / COMPENDIUMS_DIR).mkdir(parents=True)
    (path / INDEX_FILENAME).write_text(_root_index(), encoding="utf-8")
    (path / COMPENDIUMS_DIR / INDEX_FILENAME).write_text(
        _compendiums_index([]),
        encoding="utf-8",
    )


def _scan_entries(root: Path) -> list[LibraryEntry]:
    compendiums_path = root / COMPENDIUMS_DIR
    if not compendiums_path.exists():
        return []
    entries = [
        _entry_from_directory(child, root=root)
        for child in compendiums_path.iterdir()
        if child.is_dir() and not child.is_symlink()
    ]
    return sorted(entries, key=lambda entry: (entry.title.lower(), entry.id))


def _entry_from_directory(path: Path, *, root: Path) -> LibraryEntry:
    concept = read_concept(path / COMPENDIUM_FILENAME)
    fields = concept.frontmatter
    tags = fields.get("tags") or []
    timestamp = fields["timestamp"]
    if not isinstance(timestamp, datetime):
        timestamp = datetime.fromisoformat(str(timestamp))
    return LibraryEntry(
        id=str(fields["id"]),
        title=str(fields["title"]),
        description=str(fields.get("description") or ""),
        tags=tuple(str(tag) for tag in tags),
        timestamp=timestamp,
        path=path.relative_to(root).as_posix(),
    )


def _choose_entry_id(
    entries: list[LibraryEntry],
    preferred_id: str,
    title: str,
) -> str:
    if not preferred_id:
        raise LibraryError("Compendium title does not produce a usable id.")
    entries_by_id = {entry.id: entry for entry in entries}
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


def _root_index() -> str:
    return (
        "# Compendium Library\n\n"
        "* [Compendiums](./compendiums/) - Sourced research compendiums.\n"
    )


def _compendiums_index(entries: list[LibraryEntry]) -> str:
    lines = ["# Compendiums", ""]
    if not entries:
        lines.append("No compendiums.")
    for entry in sorted(entries, key=lambda item: (item.title.lower(), item.id)):
        description = " ".join(entry.description.split())
        lines.append(
            f"* [{_escape_link_label(entry.title)}](./{entry.id}/)"
            f" - {description}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _read_bundle_files(path: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for candidate in sorted(path.rglob("*.md")):
        files[candidate.relative_to(path).as_posix()] = candidate.read_text(
            encoding="utf-8"
        )
    return files


def _replace_frontmatter_value(
    content: str,
    key: str,
    value: Any,
) -> str:
    concept = parse_concept(content)
    fields = dict(concept.frontmatter)
    fields[key] = value
    frontmatter = yaml.safe_dump(
        fields,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    return f"---\n{frontmatter}\n---\n{concept.body}"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_directory(
    candidate: Path,
    destination: Path,
    staging_parent: Path,
) -> None:
    backup = staging_parent / f"{destination.name}.previous"
    if destination.exists():
        os.replace(destination, backup)
    try:
        os.replace(candidate, destination)
    except Exception:
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _same_title(left: str, right: str) -> bool:
    return " ".join(left.lower().split()) == " ".join(right.lower().split())


def _escape_link_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _issues_message(
    heading: str,
    issues: tuple[ValidationIssue, ...],
) -> str:
    rendered = "\n".join(f"- {issue}" for issue in issues)
    return f"{heading}:\n{rendered}"


def _deduplicate_issues(
    issues: list[ValidationIssue],
) -> tuple[ValidationIssue, ...]:
    return tuple(
        sorted(
            set(issues),
            key=lambda issue: (issue.path, issue.code, issue.message),
        )
    )


__all__ = [
    "COMPENDIUMS_DIR",
    "LibraryError",
    "import_compendium",
    "list_library_entries",
    "publish_compendium",
    "validate_library",
]
