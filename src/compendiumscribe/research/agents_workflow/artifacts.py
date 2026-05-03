from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


SourceStatus = Literal["cited", "consulted", "rejected"]
VerificationStatus = Literal["accepted", "follow_up", "failed"]


class ResearchSource(BaseModel):
    title: str
    url: str
    publisher: str | None = None
    published_at: str | None = None
    summary: str | None = None
    credibility_notes: str | None = None
    status: SourceStatus = "consulted"


class ResearchSection(BaseModel):
    id: str
    title: str
    focus: str
    guiding_questions: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    title: str
    primary_objective: str
    audience: str
    key_sections: list[ResearchSection]
    research_questions: list[str] = Field(default_factory=list)
    methodology_preferences: list[str] = Field(default_factory=list)
    topic_flags: list[str] = Field(default_factory=list)


class ResearchAgenda(BaseModel):
    sections: list[ResearchSection]
    source_strategy: list[str] = Field(default_factory=list)
    verification_focus: list[str] = Field(default_factory=list)


class SectionFinding(BaseModel):
    title: str
    evidence: str
    implications: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class SectionResearchBrief(BaseModel):
    section_id: str
    title: str
    summary: str
    key_terms: list[str] = Field(default_factory=list)
    guiding_questions: list[str] = Field(default_factory=list)
    findings: list[SectionFinding] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class SourceLedgerEntry(BaseModel):
    id: str
    title: str
    url: str
    publisher: str | None = None
    published_at: str | None = None
    summary: str | None = None
    credibility_notes: str | None = None
    status: SourceStatus = "consulted"
    section_ids: list[str] = Field(default_factory=list)


class SourceLedger(BaseModel):
    entries: list[SourceLedgerEntry] = Field(default_factory=list)


class VerificationIssue(BaseModel):
    section_id: str | None = None
    message: str
    severity: Literal["warning", "error"] = "warning"
    suggested_follow_up: str | None = None


class VerificationReport(BaseModel):
    status: VerificationStatus
    issues: list[VerificationIssue] = Field(default_factory=list)
    follow_up_section_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


class InsightPayload(BaseModel):
    title: str
    evidence: str
    implications: str | None = None
    citations: list[str]


class SectionPayload(BaseModel):
    id: str
    title: str
    summary: str
    key_terms: list[str] = Field(default_factory=list)
    guiding_questions: list[str] = Field(default_factory=list)
    insights: list[InsightPayload] = Field(default_factory=list)


class CitationPayload(BaseModel):
    id: str
    title: str
    url: str
    publisher: str | None = None
    published_at: str | None = None
    summary: str | None = None


class CompendiumPayload(BaseModel):
    topic_overview: str
    methodology: list[str] = Field(default_factory=list)
    sections: list[SectionPayload] = Field(default_factory=list)
    citations: list[CitationPayload] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ResearchRunState(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    topic: str
    title: str | None = None
    stage: str = "created"
    output_formats: list[str] = Field(default_factory=list)
    cost_report_path: str | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    completed_stages: list[str] = Field(default_factory=list)
    response_ids: dict[str, list[str]] = Field(default_factory=dict)
    plan: ResearchPlan | None = None
    agenda: ResearchAgenda | None = None
    section_briefs: dict[str, SectionResearchBrief] = Field(default_factory=dict)
    follow_up_done: bool = False
    ledger: SourceLedger = Field(default_factory=SourceLedger)
    verification: VerificationReport | None = None
    final_payload: CompendiumPayload | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def mark_completed(self, stage: str) -> None:
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.stage = stage
        self.updated_at = datetime.now(timezone.utc)


def validate_compendium_citations(
    payload: CompendiumPayload,
    ledger: SourceLedger,
) -> None:
    prepare_compendium_payload(payload, ledger)


def prepare_compendium_payload(
    payload: CompendiumPayload,
    ledger: SourceLedger,
) -> CompendiumPayload:
    cited_entries = {
        entry.id: entry for entry in ledger.entries if entry.status == "cited"
    }

    missing: list[str] = []
    ordered_refs: list[str] = []
    seen_refs: set[str] = set()
    for section in payload.sections:
        for insight in section.insights:
            for ref in insight.citations:
                if ref not in cited_entries:
                    missing.append(ref)
                    continue
                if ref not in seen_refs:
                    seen_refs.add(ref)
                    ordered_refs.append(ref)
    if missing:
        refs = ", ".join(sorted(set(missing)))
        raise ValueError(f"Final payload references unknown citation IDs: {refs}")

    citations: list[CitationPayload] = []
    for ref in ordered_refs:
        entry = cited_entries[ref]
        citations.append(
            CitationPayload(
                id=entry.id,
                title=entry.title,
                url=entry.url,
                publisher=entry.publisher,
                published_at=entry.published_at,
                summary=entry.summary,
            )
        )
    return payload.model_copy(update={"citations": citations})


__all__ = [
    "CitationPayload",
    "CompendiumPayload",
    "InsightPayload",
    "prepare_compendium_payload",
    "ResearchAgenda",
    "ResearchPlan",
    "ResearchRunState",
    "ResearchSection",
    "ResearchSource",
    "SectionFinding",
    "SectionPayload",
    "SectionResearchBrief",
    "SourceLedger",
    "SourceLedgerEntry",
    "VerificationIssue",
    "VerificationReport",
    "validate_compendium_citations",
]
