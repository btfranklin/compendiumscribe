from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from .artifacts import (
    ResearchSource,
    SectionResearchBrief,
    SourceLedger,
    SourceLedgerEntry,
)


def normalize_url(url: str) -> str:
    raw_url = url.strip()
    parsed = urlsplit(raw_url)
    if not parsed.scheme and not parsed.netloc and _looks_like_host_path(parsed.path):
        parsed = urlsplit(f"https://{raw_url}")
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def _looks_like_host_path(path: str) -> bool:
    host = path.split("/", 1)[0]
    return bool(host) and ("." in host or host == "localhost")


def build_source_ledger(
    briefs: list[SectionResearchBrief],
    *,
    existing: SourceLedger | None = None,
) -> SourceLedger:
    ledger = existing or SourceLedger()
    by_url = {normalize_url(entry.url): entry for entry in ledger.entries}

    for brief in briefs:
        for source in brief.sources:
            if source.status == "rejected":
                continue
            normalized = normalize_url(source.url)
            entry = by_url.get(normalized)
            if entry is None:
                entry = _entry_from_source(
                    source,
                    identifier=f"C{len(by_url) + 1:02d}",
                    section_id=brief.section_id,
                )
                by_url[normalized] = entry
                ledger.entries.append(entry)
                continue

            if brief.section_id not in entry.section_ids:
                entry.section_ids.append(brief.section_id)
            if entry.status != "cited" and source.status == "cited":
                entry.status = "cited"

    return ledger


def mark_cited_sources(
    ledger: SourceLedger,
    cited_urls: list[str],
) -> SourceLedger:
    cited = {normalize_url(url) for url in cited_urls if url}
    for entry in ledger.entries:
        if normalize_url(entry.url) in cited:
            entry.status = "cited"
    return ledger


def _entry_from_source(
    source: ResearchSource,
    *,
    identifier: str,
    section_id: str,
) -> SourceLedgerEntry:
    return SourceLedgerEntry(
        id=identifier,
        title=source.title,
        url=normalize_url(source.url),
        publisher=source.publisher,
        published_at=source.published_at,
        summary=source.summary,
        credibility_notes=source.credibility_notes,
        status=source.status,
        section_ids=[section_id],
    )


__all__ = [
    "build_source_ledger",
    "mark_cited_sources",
    "normalize_url",
]
