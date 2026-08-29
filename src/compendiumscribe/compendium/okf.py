from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
import os
import re
import shutil
import tempfile
from typing import Any, TYPE_CHECKING

import mistune
import yaml

from .entities import Citation, Insight, Section
from .source_metadata import normalize_accessed_at, normalize_revision
from .text_utils import slugify

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from .compendium import Compendium


PROFILE_NAME = "compendiumscribe"
PROFILE_VERSION = "1"
COMPENDIUM_FILENAME = "compendium.md"
INDEX_FILENAME = "index.md"
SECTIONS_DIR = "sections"
SOURCES_DIR = "sources"
MAX_DESCRIPTION_CHARS = 500
MAX_TAGS = 14

_MARKDOWN_AST = mistune.create_markdown(renderer="ast")
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


class OKFError(RuntimeError):
    """Raised when an OKF bundle cannot be rendered, parsed, or written."""


@dataclass(frozen=True)
class ValidationIssue:
    """One stable, user-facing OKF validation problem."""

    path: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: [{self.code}] {self.message}"


@dataclass(frozen=True)
class ConceptDocument:
    """Parsed OKF concept document."""

    frontmatter: dict[str, Any]
    body: str


def render_okf_bundle(
    compendium: Compendium,
    *,
    compendium_id: str | None = None,
) -> dict[str, str]:
    """Render a Compendium into the CompendiumScribe OKF profile."""

    section_paths = _identifier_paths(
        ((section.identifier, section) for section in compendium.sections),
        directory=SECTIONS_DIR,
        kind="section",
    )
    source_paths = _identifier_paths(
        ((citation.identifier, citation) for citation in compendium.citations),
        directory=SOURCES_DIR,
        kind="source",
    )
    source_by_id = {
        citation.identifier: source_paths[citation.identifier]
        for citation in compendium.citations
    }
    _validate_citation_refs(compendium.sections, source_by_id)

    timestamp = _format_timestamp(compendium.generated_at)
    resolved_compendium_id = compendium_id or slugify(compendium.topic)
    if not resolved_compendium_id:
        raise OKFError("Compendium topic does not produce a usable OKF id.")

    files = {
        INDEX_FILENAME: _render_compendium_index(compendium),
        COMPENDIUM_FILENAME: _render_compendium_document(
            compendium,
            compendium_id=resolved_compendium_id,
            timestamp=timestamp,
        ),
        f"{SECTIONS_DIR}/{INDEX_FILENAME}": _render_sections_index(
            compendium.sections,
            section_paths,
        ),
        f"{SOURCES_DIR}/{INDEX_FILENAME}": _render_sources_index(
            compendium.citations,
            source_paths,
        ),
    }

    for section in compendium.sections:
        files[section_paths[section.identifier]] = _render_section_document(
            section,
            timestamp=timestamp,
            source_paths=source_by_id,
        )
    for citation in compendium.citations:
        files[source_paths[citation.identifier]] = _render_source_document(
            citation,
            timestamp=timestamp,
        )

    issues = validate_okf_mapping(files)
    if issues:
        raise OKFError(_issues_message("Generated OKF bundle is invalid", issues))
    return dict(sorted(files.items()))


def parse_okf_bundle(path: Path) -> Compendium:
    """Parse a validated CompendiumScribe OKF directory."""

    issues = validate_okf_bundle(path)
    if issues:
        raise OKFError(_issues_message(f"Invalid OKF bundle at {path}", issues))

    from .compendium import Compendium

    root = path.expanduser()
    compendium_doc = read_concept(root / COMPENDIUM_FILENAME)
    root_fields = compendium_doc.frontmatter
    root_sections = _top_level_sections(compendium_doc.body)

    section_documents = _index_document_links(
        root / SECTIONS_DIR / INDEX_FILENAME,
        expected_prefix=None,
    )
    source_documents = _index_document_links(
        root / SOURCES_DIR / INDEX_FILENAME,
        expected_prefix=None,
    )

    citations: list[Citation] = []
    for relative_name in source_documents:
        source_doc = read_concept(root / SOURCES_DIR / relative_name)
        fields = source_doc.frontmatter
        source_sections = _top_level_sections(source_doc.body)
        citations.append(
            Citation(
                identifier=str(fields["id"]),
                title=str(fields.get("title") or "Untitled Source"),
                url=str(fields.get("resource") or ""),
                publisher=_optional_string(fields.get("publisher")),
                published_at=_optional_string(fields.get("published_at")),
                revision=_optional_string(fields.get("revision")),
                accessed_at=_optional_string(fields.get("accessed_at")),
                summary=_optional_string(
                    _decode_block(source_sections.get("Summary", ""))
                ),
            )
        )

    sections: list[Section] = []
    for relative_name in section_documents:
        section_doc = read_concept(root / SECTIONS_DIR / relative_name)
        fields = section_doc.frontmatter
        body_sections = _top_level_sections(section_doc.body)
        sections.append(
            Section(
                identifier=str(fields["id"]),
                title=str(fields.get("title") or "Untitled Section"),
                summary=_decode_block(body_sections.get("Summary", "")),
                key_terms=list(fields.get("tags") or []),
                guiding_questions=_parse_list(
                    body_sections.get("Guiding Questions", "")
                ),
                insights=_parse_insights(
                    body_sections.get("Insights", ""),
                    root=root,
                    section_path=root / SECTIONS_DIR / relative_name,
                ),
            )
        )

    return Compendium(
        topic=str(root_fields.get("title") or "Untitled Compendium"),
        overview=_decode_block(root_sections.get("Overview", "")),
        methodology=_parse_list(root_sections.get("Methodology", "")),
        sections=sections,
        citations=citations,
        open_questions=_parse_list(
            root_sections.get("Open Questions", "")
        ),
        generated_at=_parse_timestamp(root_fields["timestamp"]),
    )


def write_okf_bundle(path: Path, files: Mapping[str, str]) -> None:
    """Stage, validate, and replace an OKF directory as one artifact."""

    destination = path.expanduser()
    mapping_issues = validate_okf_mapping(files)
    if mapping_issues:
        raise OKFError(
            _issues_message("Refusing to write invalid OKF bundle", mapping_issues)
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.",
            dir=destination.parent,
        )
    )
    staging = staging_parent / destination.name
    staging.mkdir()
    try:
        for relative_path, content in files.items():
            target = staging / PurePosixPath(relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        issues = validate_okf_bundle(staging)
        if issues:
            raise OKFError(
                _issues_message("Staged OKF bundle is invalid", issues)
            )

        backup = staging_parent / f"{destination.name}.previous"
        if destination.exists():
            if not destination.is_dir() or destination.is_symlink():
                raise OKFError(
                    f"OKF destination is not a directory: {destination}"
                )
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except Exception:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)


def validate_okf_bundle(path: Path) -> tuple[ValidationIssue, ...]:
    """Validate an on-disk CompendiumScribe OKF bundle."""

    root = path.expanduser()
    issues: list[ValidationIssue] = []
    if not root.exists():
        return (
            ValidationIssue(".", "bundle_missing", "Bundle does not exist."),
        )
    if not root.is_dir() or root.is_symlink():
        return (
            ValidationIssue(
                ".",
                "bundle_not_directory",
                "Bundle root must be a real directory.",
            ),
        )

    files: dict[str, str] = {}
    for candidate in sorted(root.rglob("*")):
        relative = candidate.relative_to(root).as_posix()
        if candidate.is_symlink():
            issues.append(
                ValidationIssue(
                    relative,
                    "symlink_forbidden",
                    "Symlinks are not allowed in managed OKF bundles.",
                )
            )
            continue
        if candidate.is_dir():
            continue
        if candidate.suffix.lower() != ".md":
            issues.append(
                ValidationIssue(
                    relative,
                    "non_markdown_file",
                    "Managed OKF bundles may contain only Markdown files.",
                )
            )
            continue
        try:
            files[relative] = candidate.read_text(encoding="utf-8")
        except UnicodeError:
            issues.append(
                ValidationIssue(
                    relative,
                    "invalid_utf8",
                    "OKF documents must be UTF-8.",
                )
            )

    issues.extend(validate_okf_mapping(files))
    return _deduplicate_issues(issues)


def validate_okf_mapping(
    files: Mapping[str, str],
) -> tuple[ValidationIssue, ...]:
    """Validate a mapping representing one CompendiumScribe OKF bundle."""

    issues: list[ValidationIssue] = []
    normalized_files: dict[str, str] = {}
    for supplied_path, content in files.items():
        path = PurePosixPath(supplied_path)
        if path.is_absolute() or ".." in path.parts:
            issues.append(
                ValidationIssue(
                    supplied_path,
                    "path_traversal",
                    "Bundle paths must stay below the bundle root.",
                )
            )
            continue
        normalized = path.as_posix()
        normalized_files[normalized] = content
        if path.suffix.lower() != ".md":
            issues.append(
                ValidationIssue(
                    normalized,
                    "non_markdown_file",
                    "Managed OKF bundles may contain only Markdown files.",
                )
            )
        if path.name == "log.md":
            issues.append(
                ValidationIssue(
                    normalized,
                    "log_forbidden",
                    "CompendiumScribe OKF bundles do not support log.md.",
                )
            )

    required = {
        INDEX_FILENAME,
        COMPENDIUM_FILENAME,
        f"{SECTIONS_DIR}/{INDEX_FILENAME}",
        f"{SOURCES_DIR}/{INDEX_FILENAME}",
    }
    for required_path in sorted(required - normalized_files.keys()):
        issues.append(
            ValidationIssue(
                required_path,
                "required_file_missing",
                "Required CompendiumScribe OKF file is missing.",
            )
        )

    concepts: dict[str, ConceptDocument] = {}
    for path, content in normalized_files.items():
        if PurePosixPath(path).name == INDEX_FILENAME:
            if _has_frontmatter(content):
                issues.append(
                    ValidationIssue(
                        path,
                        "index_frontmatter",
                        "Index files must not contain frontmatter.",
                    )
                )
            _validate_index(path, content, normalized_files, issues)
            continue
        try:
            concept = parse_concept(content)
        except OKFError as exc:
            issues.append(
                ValidationIssue(path, "invalid_frontmatter", str(exc))
            )
            continue
        concepts[path] = concept
        _validate_common_frontmatter(path, concept.frontmatter, issues)

    compendium_doc = concepts.get(COMPENDIUM_FILENAME)
    if compendium_doc is not None:
        fields = compendium_doc.frontmatter
        _validate_profile_frontmatter(COMPENDIUM_FILENAME, fields, issues)
        _require_exact(
            fields,
            COMPENDIUM_FILENAME,
            "type",
            "Compendium",
            issues,
        )
        _require_exact(
            fields,
            COMPENDIUM_FILENAME,
            "profile",
            PROFILE_NAME,
            issues,
        )
        _require_exact(
            fields,
            COMPENDIUM_FILENAME,
            "profile_version",
            PROFILE_VERSION,
            issues,
        )
        _validate_body_headings(
            COMPENDIUM_FILENAME,
            compendium_doc.body,
            ("Overview", "Methodology", "Open Questions"),
            issues,
        )

    identifiers: dict[str, str] = {}
    source_ids: dict[str, str] = {}
    for path, concept in concepts.items():
        fields = concept.frontmatter
        identifier = fields.get("id")
        if isinstance(identifier, str) and identifier.strip():
            normalized_id = slugify(identifier)
            previous = identifiers.get(normalized_id)
            if previous is not None and previous != path:
                issues.append(
                    ValidationIssue(
                        path,
                        "duplicate_normalized_id",
                        f"ID collides with {previous} after normalization.",
                    )
                )
            else:
                identifiers[normalized_id] = path

        if path.startswith(f"{SECTIONS_DIR}/"):
            _validate_profile_frontmatter(path, fields, issues)
            _require_exact(
                fields,
                path,
                "type",
                "Compendium Section",
                issues,
            )
            _validate_body_headings(
                path,
                concept.body,
                ("Summary", "Guiding Questions", "Insights"),
                issues,
            )
        elif path.startswith(f"{SOURCES_DIR}/"):
            _validate_profile_frontmatter(path, fields, issues)
            _require_exact(fields, path, "type", "Source", issues)
            _require_value(fields, path, "resource", issues)
            _validate_source_metadata(path, fields, issues)
            _validate_body_headings(
                path,
                concept.body,
                ("Summary", "Citation"),
                issues,
            )
            if isinstance(identifier, str):
                source_ids[identifier] = path

    _validate_profile_links(
        normalized_files,
        concepts,
        source_ids,
        issues,
    )
    return _deduplicate_issues(issues)


def parse_concept(content: str) -> ConceptDocument:
    """Parse one OKF concept document."""

    if not content.startswith("---\n"):
        raise OKFError("Concept document must start with YAML frontmatter.")
    closing = content.find("\n---\n", 4)
    if closing < 0:
        raise OKFError("Concept frontmatter is missing its closing delimiter.")
    raw_frontmatter = content[4:closing]
    try:
        loaded = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError as exc:
        raise OKFError(f"Frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise OKFError("Concept frontmatter must be a YAML mapping.")
    body = content[closing + 5 :]
    return ConceptDocument(frontmatter=dict(loaded), body=body)


def read_concept(path: Path) -> ConceptDocument:
    """Read and parse one concept from disk."""

    try:
        return parse_concept(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise OKFError(f"Failed to read OKF concept {path}: {exc}") from exc


def derive_compendium_tags(compendium: Compendium) -> list[str]:
    """Derive compact deterministic tags from the existing Compendium model."""

    candidates: list[str] = []
    candidates.extend(_tokenize(compendium.topic))
    for section in compendium.sections:
        candidates.extend(_tokenize(section.title))
        candidates.extend(_normalize_tag(term) for term in section.key_terms)

    tags: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in _STOP_WORDS or candidate in seen:
            continue
        seen.add(candidate)
        tags.append(candidate)
        if len(tags) >= MAX_TAGS:
            break
    return tags


def _render_compendium_index(compendium: Compendium) -> str:
    lines = [
        f"# {_encode_inline(compendium.topic)}",
        "",
        (
            f"* [Compendium](./{COMPENDIUM_FILENAME}) - "
            f"{_one_line(compendium.overview)}"
        ).rstrip(),
        f"* [Sections](./{SECTIONS_DIR}/) - Research sections and insights.",
        f"* [Sources](./{SOURCES_DIR}/) - Cited source records.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _render_compendium_document(
    compendium: Compendium,
    *,
    compendium_id: str,
    timestamp: str,
) -> str:
    frontmatter = {
        "type": "Compendium",
        "id": compendium_id,
        "title": compendium.topic,
        "description": _description(compendium.overview),
        "tags": derive_compendium_tags(compendium),
        "timestamp": timestamp,
        "profile": PROFILE_NAME,
        "profile_version": PROFILE_VERSION,
    }
    body = _render_named_sections(
        (
            ("Overview", _encode_block(compendium.overview)),
            ("Methodology", _render_list(compendium.methodology)),
            ("Open Questions", _render_list(compendium.open_questions)),
        )
    )
    return _document(frontmatter, body)


def _render_sections_index(
    sections: list[Section],
    paths: Mapping[str, str],
) -> str:
    lines = ["# Sections", ""]
    if not sections:
        lines.append("No sections.")
    for section in sections:
        filename = PurePosixPath(paths[section.identifier]).name
        lines.append(
            f"* [{_encode_link_label(section.title)}](./{filename})"
            f" - {_one_line(section.summary)}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_sources_index(
    citations: list[Citation],
    paths: Mapping[str, str],
) -> str:
    lines = ["# Sources", ""]
    if not citations:
        lines.append("No sources.")
    for citation in citations:
        filename = PurePosixPath(paths[citation.identifier]).name
        lines.append(
            f"* [{_encode_link_label(citation.title)}](./{filename})"
            f" - {_one_line(citation.summary or '')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_section_document(
    section: Section,
    *,
    timestamp: str,
    source_paths: Mapping[str, str],
) -> str:
    frontmatter = {
        "type": "Compendium Section",
        "id": section.identifier,
        "title": section.title,
        "description": _description(section.summary),
        "tags": list(section.key_terms),
        "timestamp": timestamp,
    }
    insight_lines: list[str] = []
    for insight in section.insights:
        if insight_lines:
            insight_lines.append("")
        insight_lines.extend(
            [
                f"## {_encode_inline(insight.title)}",
                "",
                "### Evidence",
                "",
                _encode_block(insight.evidence),
            ]
        )
        if insight.implications:
            insight_lines.extend(
                [
                    "",
                    "### Implications",
                    "",
                    _encode_block(insight.implications),
                ]
            )
        insight_lines.extend(["", "### Citations", ""])
        for reference in insight.citation_refs:
            source_filename = PurePosixPath(source_paths[reference]).name
            insight_lines.append(
                f"* [{_encode_link_label(reference)}]"
                f"(../{SOURCES_DIR}/{source_filename})"
            )

    body = _render_named_sections(
        (
            ("Summary", _encode_block(section.summary)),
            (
                "Guiding Questions",
                _render_list(section.guiding_questions),
            ),
            ("Insights", "\n".join(insight_lines)),
        )
    )
    return _document(frontmatter, body)


def _render_source_document(
    citation: Citation,
    *,
    timestamp: str,
) -> str:
    frontmatter: dict[str, Any] = {
        "type": "Source",
        "id": citation.identifier,
        "title": citation.title,
        "description": _description(citation.summary or ""),
        "resource": citation.url,
        "timestamp": timestamp,
    }
    if citation.publisher:
        frontmatter["publisher"] = citation.publisher
    if citation.published_at:
        frontmatter["published_at"] = citation.published_at
    if citation.revision:
        frontmatter["revision"] = citation.revision
    if citation.accessed_at:
        frontmatter["accessed_at"] = citation.accessed_at

    citation_link = (
        f"[{_encode_link_label(citation.title)}]"
        f"({_encode_link_target(citation.url)})"
    )
    body = _render_named_sections(
        (
            ("Summary", _encode_block(citation.summary or "")),
            ("Citation", citation_link),
        )
    )
    return _document(frontmatter, body)


def _document(frontmatter: Mapping[str, Any], body: str) -> str:
    dumped = yaml.safe_dump(
        dict(frontmatter),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    return f"---\n{dumped}\n---\n\n{body.rstrip()}\n"


def _render_named_sections(sections: Iterable[tuple[str, str]]) -> str:
    parts: list[str] = []
    for heading, content in sections:
        parts.append(f"# {heading}")
        if content:
            parts.extend(["", content.rstrip()])
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _identifier_paths(
    items: Iterable[tuple[str, object]],
    *,
    directory: str,
    kind: str,
) -> dict[str, str]:
    paths: dict[str, str] = {}
    normalized_ids: dict[str, str] = {}
    for identifier, _item in items:
        filename = slugify(identifier)
        if not filename:
            raise OKFError(f"{kind.title()} id {identifier!r} is not usable.")
        previous = normalized_ids.get(filename)
        if previous is not None:
            raise OKFError(
                f"{kind.title()} ids {previous!r} and {identifier!r} "
                "collide after filename normalization."
            )
        normalized_ids[filename] = identifier
        paths[identifier] = f"{directory}/{filename}.md"
    return paths


def _validate_citation_refs(
    sections: Iterable[Section],
    source_paths: Mapping[str, str],
) -> None:
    for section in sections:
        for insight in section.insights:
            for reference in insight.citation_refs:
                if reference not in source_paths:
                    raise OKFError(
                        f"Insight {insight.title!r} references unknown "
                        f"citation id {reference!r}."
                    )


def _format_timestamp(value: datetime) -> str:
    return value.isoformat()


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _description(value: str) -> str:
    text = _one_line(value)
    if len(text) <= MAX_DESCRIPTION_CHARS:
        return text
    shortened = text[: MAX_DESCRIPTION_CHARS - 3].rsplit(" ", 1)[0].rstrip()
    return f"{shortened or text[: MAX_DESCRIPTION_CHARS - 3].rstrip()}..."


def _one_line(value: str) -> str:
    return " ".join((value or "").split())


def _tokenize(value: str) -> list[str]:
    return [
        token
        for token in (
            _normalize_tag(match.group(0))
            for match in re.finditer(r"[A-Za-z][A-Za-z0-9-]*", value or "")
        )
        if token
    ]


def _normalize_tag(value: str | None) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip().lower())
    normalized = normalized.strip(".,;:!?()[]{}\"'")
    return normalized if len(normalized) >= 3 else ""


def _encode_block(value: str) -> str:
    encoded: list[str] = []
    for line in (value or "").replace("\r\n", "\n").replace("\r", "\n").split(
        "\n"
    ):
        escaped = line.replace("\\", "\\\\")
        if escaped.startswith("#"):
            escaped = f"\\{escaped}"
        encoded.append(escaped)
    return "\n".join(encoded).strip("\n")


def _decode_block(value: str) -> str:
    decoded: list[str] = []
    for line in value.strip("\n").split("\n"):
        current = line
        if current.startswith("\\#"):
            current = current[1:]
        decoded.append(_unescape_backslashes(current))
    return "\n".join(decoded)


def _encode_inline(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def _decode_inline(value: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\" or index + 1 >= len(value):
            result.append(char)
            index += 1
            continue
        next_char = value[index + 1]
        if next_char == "n":
            result.append("\n")
        else:
            result.append(next_char)
        index += 2
    return "".join(result)


def _unescape_backslashes(value: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            result.append(value[index + 1])
            index += 2
        else:
            result.append(value[index])
            index += 1
    return "".join(result)


def _encode_link_label(value: str) -> str:
    return _encode_inline(value).replace("[", "\\[").replace("]", "\\]")


def _encode_link_target(value: str) -> str:
    return (value or "").replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def _render_list(values: Iterable[str]) -> str:
    return "\n".join(f"* {_encode_inline(value)}" for value in values)


def _parse_list(content: str) -> list[str]:
    values: list[str] = []
    for line in content.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith(("* ", "- ")):
            values.append(_decode_inline(stripped[2:]))
    return values


def _top_level_sections(body: str) -> dict[str, str]:
    _MARKDOWN_AST(body)
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        if line.startswith("# ") and not line.startswith("\\# "):
            current = line[2:].strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {
        heading: "\n".join(lines).strip("\n")
        for heading, lines in sections.items()
    }


def _parse_insights(
    content: str,
    *,
    root: Path,
    section_path: Path,
) -> list[Insight]:
    insights: list[Insight] = []
    blocks: list[tuple[str, list[str]]] = []
    title: str | None = None
    lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## ") and not line.startswith("\\## "):
            if title is not None:
                blocks.append((title, lines))
            title = _decode_inline(line[3:].strip())
            lines = []
        elif title is not None:
            lines.append(line)
    if title is not None:
        blocks.append((title, lines))

    for insight_title, block_lines in blocks:
        subsections = _heading_sections(block_lines, level=3)
        citation_refs: list[str] = []
        for raw_line in subsections.get("Citations", "").splitlines():
            match = re.match(r"^\s*[*-]\s+\[(.+)]\((.+)\)\s*$", raw_line)
            if not match:
                continue
            label = _decode_inline(
                match.group(1).replace("\\[", "[").replace("\\]", "]")
            )
            target = _resolve_bundle_link(
                root=root,
                source=section_path,
                target=match.group(2),
            )
            if target is not None and target.parts[-2] == SOURCES_DIR:
                citation_refs.append(label)
        insights.append(
            Insight(
                title=insight_title,
                evidence=_decode_block(subsections.get("Evidence", "")),
                implications=_optional_string(
                    _decode_block(subsections.get("Implications", ""))
                ),
                citation_refs=citation_refs,
            )
        )
    return insights


def _heading_sections(lines: list[str], *, level: int) -> dict[str, str]:
    prefix = f"{'#' * level} "
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith(prefix) and not line.startswith(f"\\{prefix}"):
            current = line[len(prefix) :].strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {
        heading: "\n".join(section_lines).strip("\n")
        for heading, section_lines in sections.items()
    }


def _index_document_links(
    index_path: Path,
    *,
    expected_prefix: str | None,
) -> list[str]:
    content = index_path.read_text(encoding="utf-8")
    links = _markdown_links(content)
    names: list[str] = []
    for _label, target in links:
        cleaned = target.removeprefix("./")
        if expected_prefix and not cleaned.startswith(expected_prefix):
            continue
        if cleaned.endswith(".md"):
            names.append(PurePosixPath(cleaned).name)
    return names


def _markdown_links(content: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in re.finditer(r"\[([^\]]+(?:\\\][^\]]*)*)]\(([^)]+)\)", content):
        links.append((match.group(1), match.group(2)))
    return links


def _validate_index(
    path: str,
    content: str,
    files: Mapping[str, str],
    issues: list[ValidationIssue],
) -> None:
    ast = _MARKDOWN_AST(content)
    if not any(token.get("type") == "heading" for token in ast):
        issues.append(
            ValidationIssue(
                path,
                "index_heading_missing",
                "Index must contain a Markdown heading.",
            )
        )
    for _label, target in _markdown_links(content):
        if "://" in target or target.startswith("mailto:"):
            continue
        resolved = _resolve_mapping_link(path, target)
        if resolved is None:
            issues.append(
                ValidationIssue(
                    path,
                    "path_traversal",
                    f"Index link escapes the bundle: {target}",
                )
            )
            continue
        if resolved.endswith("/"):
            resolved = f"{resolved}{INDEX_FILENAME}"
        if resolved not in files:
            issues.append(
                ValidationIssue(
                    path,
                    "broken_index_link",
                    f"Index link target does not exist: {target}",
                )
            )


def _validate_common_frontmatter(
    path: str,
    fields: Mapping[str, Any],
    issues: list[ValidationIssue],
) -> None:
    _require_value(fields, path, "type", issues)
    tags = fields.get("tags")
    if tags is not None and (
        not isinstance(tags, list)
        or any(not isinstance(tag, str) for tag in tags)
    ):
        issues.append(
            ValidationIssue(
                path,
                "invalid_tags",
                "Frontmatter tags must be a YAML list of strings.",
            )
        )
    timestamp = fields.get("timestamp")
    if timestamp is not None:
        try:
            _parse_timestamp(timestamp)
        except (TypeError, ValueError):
            issues.append(
                ValidationIssue(
                    path,
                    "invalid_timestamp",
                    "Frontmatter timestamp must be ISO 8601.",
                )
            )


def _validate_profile_frontmatter(
    path: str,
    fields: Mapping[str, Any],
    issues: list[ValidationIssue],
) -> None:
    for name in ("id", "title", "timestamp"):
        _require_value(fields, path, name, issues)


def _validate_source_metadata(
    path: str,
    fields: Mapping[str, Any],
    issues: list[ValidationIssue],
) -> None:
    if "revision" in fields:
        try:
            normalize_revision(fields["revision"])
        except ValueError:
            issues.append(
                ValidationIssue(
                    path,
                    "invalid_revision",
                    "Source revision must be a non-empty string.",
                )
            )
    if "accessed_at" in fields:
        try:
            normalize_accessed_at(fields["accessed_at"])
        except ValueError:
            issues.append(
                ValidationIssue(
                    path,
                    "invalid_accessed_at",
                    "Source accessed_at must be a timezone-aware ISO 8601 timestamp.",
                )
            )


def _validate_body_headings(
    path: str,
    body: str,
    expected: tuple[str, ...],
    issues: list[ValidationIssue],
) -> None:
    sections = _top_level_sections(body)
    missing = [heading for heading in expected if heading not in sections]
    if missing:
        issues.append(
            ValidationIssue(
                path,
                "profile_heading_missing",
                f"Missing required profile heading(s): {', '.join(missing)}.",
            )
        )


def _validate_profile_links(
    files: Mapping[str, str],
    concepts: Mapping[str, ConceptDocument],
    source_ids: Mapping[str, str],
    issues: list[ValidationIssue],
) -> None:
    for path, concept in concepts.items():
        if not path.startswith(f"{SECTIONS_DIR}/"):
            continue
        sections = _top_level_sections(concept.body)
        for _label, target in _markdown_links(sections.get("Insights", "")):
            if "://" in target or target.startswith("mailto:"):
                continue
            resolved = _resolve_mapping_link(path, target)
            if resolved is None:
                issues.append(
                    ValidationIssue(
                        path,
                        "path_traversal",
                        f"Citation link escapes the bundle: {target}",
                    )
                )
            elif resolved not in files:
                issues.append(
                    ValidationIssue(
                        path,
                        "broken_source_link",
                        f"Citation link target does not exist: {target}",
                    )
                )

    for source_id, source_path in source_ids.items():
        expected_filename = f"{slugify(source_id)}.md"
        if PurePosixPath(source_path).name != expected_filename:
            issues.append(
                ValidationIssue(
                    source_path,
                    "id_filename_mismatch",
                    "Source filename must be the normalized source id.",
                )
            )


def _resolve_mapping_link(source: str, target: str) -> str | None:
    if "://" in target or target.startswith("mailto:"):
        return target
    clean_target = target.split("#", 1)[0]
    source_parent = PurePosixPath(source).parent
    if clean_target.startswith("/"):
        parts = list(PurePosixPath(clean_target.lstrip("/")).parts)
    else:
        parts = list(source_parent.parts) + list(
            PurePosixPath(clean_target).parts
        )
    normalized: list[str] = []
    for part in parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not normalized:
                return None
            normalized.pop()
        else:
            normalized.append(part)
    result = PurePosixPath(*normalized).as_posix()
    if clean_target.endswith("/"):
        result += "/"
    return result


def _resolve_bundle_link(
    *,
    root: Path,
    source: Path,
    target: str,
) -> Path | None:
    if "://" in target or target.startswith("mailto:"):
        return None
    raw = target.split("#", 1)[0]
    candidate = (
        root / raw.lstrip("/")
        if raw.startswith("/")
        else source.parent / raw
    ).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _require_value(
    fields: Mapping[str, Any],
    path: str,
    name: str,
    issues: list[ValidationIssue],
) -> None:
    value = fields.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        issues.append(
            ValidationIssue(
                path,
                "required_field_missing",
                f"Required frontmatter field {name!r} is missing or empty.",
            )
        )


def _require_exact(
    fields: Mapping[str, Any],
    path: str,
    name: str,
    expected: str,
    issues: list[ValidationIssue],
) -> None:
    if fields.get(name) != expected:
        issues.append(
            ValidationIssue(
                path,
                "profile_field_invalid",
                f"Frontmatter field {name!r} must be {expected!r}.",
            )
        )


def _has_frontmatter(content: str) -> bool:
    return content.startswith("---\n")


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _deduplicate_issues(
    issues: Iterable[ValidationIssue],
) -> tuple[ValidationIssue, ...]:
    return tuple(
        sorted(
            set(issues),
            key=lambda issue: (issue.path, issue.code, issue.message),
        )
    )


def _issues_message(
    heading: str,
    issues: Iterable[ValidationIssue],
) -> str:
    rendered = "\n".join(f"- {issue}" for issue in issues)
    return f"{heading}:\n{rendered}"


__all__ = [
    "COMPENDIUM_FILENAME",
    "INDEX_FILENAME",
    "OKFError",
    "PROFILE_NAME",
    "PROFILE_VERSION",
    "SECTIONS_DIR",
    "SOURCES_DIR",
    "ValidationIssue",
    "derive_compendium_tags",
    "parse_concept",
    "parse_okf_bundle",
    "read_concept",
    "render_okf_bundle",
    "validate_okf_bundle",
    "validate_okf_mapping",
    "write_okf_bundle",
]
