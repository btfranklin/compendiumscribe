from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from contract4agents.tracing import TraceAttempt
from pydantic import BaseModel, Field

from ...agent_contracts.generated.python import (
    CitationPayload,
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    SectionResearchBrief,
    SourceLedger,
    VerificationReport,
)


class CompletedAgentStage(BaseModel):
    """Durable host evidence for one accepted semantic stage output."""

    stage: str
    agent_name: str
    output_type: str
    output: dict[str, Any]
    invocation_id: str
    attempt_id: str
    attempt_number: int
    retry_of: str | None = None

    @property
    def attempt(self) -> TraceAttempt:
        return TraceAttempt(
            invocation_id=self.invocation_id,
            attempt_id=self.attempt_id,
            number=self.attempt_number,
            retry_of=self.retry_of,
        )


class ResearchRunState(BaseModel):
    """Host-owned resumable workflow state outside the portable contract types."""

    run_id: str = Field(default_factory=lambda: uuid4().hex)
    topic: str
    title: str | None = None
    stage: str = "created"
    output_formats: list[str] = Field(default_factory=list)
    cost_report_path: str | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    completed_stages: list[str] = Field(default_factory=list)
    response_ids: dict[str, list[str]] = Field(default_factory=dict)
    attempt_counts: dict[str, int] = Field(default_factory=dict)
    agent_stages: dict[str, CompletedAgentStage] = Field(default_factory=dict)
    plan: ResearchPlan | None = None
    agenda: ResearchAgenda | None = None
    section_briefs: dict[str, SectionResearchBrief] = Field(default_factory=dict)
    follow_up_done: bool = False
    ledger: SourceLedger = Field(default_factory=lambda: SourceLedger(entries=[]))
    verification: VerificationReport | None = None
    final_payload: CompendiumPayload | None = None
    run_spec_selection: dict[str, Any] | None = None
    run_spec_result: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def mark_completed(self, stage: str) -> None:
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.stage = stage
        self.updated_at = datetime.now(timezone.utc)


def prepare_compendium_payload(
    payload: CompendiumPayload,
    ledger: SourceLedger,
) -> CompendiumPayload:
    """Resolve final citations from the accepted host-owned source ledger."""

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

    citations = [
        CitationPayload(
            id=cited_entries[ref].id,
            title=cited_entries[ref].title,
            url=cited_entries[ref].url,
            publisher=cited_entries[ref].publisher,
            published_at=cited_entries[ref].published_at,
            summary=cited_entries[ref].summary,
        )
        for ref in ordered_refs
    ]
    return payload.model_copy(update={"citations": citations})


__all__ = [
    "CompletedAgentStage",
    "ResearchRunState",
    "prepare_compendium_payload",
]
