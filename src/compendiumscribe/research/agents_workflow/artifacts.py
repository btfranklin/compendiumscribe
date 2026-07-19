from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from ...agent_contracts.generated.python import (
    CitationPayload,
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    SectionResearchBrief,
    SourceLedger,
    VerificationReport,
)


SOURCE_STATUSES = frozenset({"cited", "consulted", "rejected"})
VERIFICATION_STATUSES = frozenset({"accepted", "follow_up", "failed"})
VERIFICATION_SEVERITIES = frozenset({"warning", "error"})


def validate_artifact_semantics(artifact: BaseModel) -> None:
    """Validate value sets that canonical generated types represent as strings."""

    if isinstance(artifact, SectionResearchBrief):
        _require_known_values(
            "research source status",
            (source.status for source in artifact.sources),
            SOURCE_STATUSES,
        )
    if isinstance(artifact, SourceLedger):
        _require_known_values(
            "source ledger status",
            (entry.status for entry in artifact.entries),
            SOURCE_STATUSES,
        )
    if isinstance(artifact, VerificationReport):
        _require_known_values(
            "verification status",
            (artifact.status,),
            VERIFICATION_STATUSES,
        )
        _require_known_values(
            "verification issue severity",
            (issue.severity for issue in artifact.issues),
            VERIFICATION_SEVERITIES,
        )


def _require_known_values(
    label: str,
    values: Any,
    allowed: frozenset[str],
) -> None:
    invalid = sorted(set(values) - allowed)
    if invalid:
        raise ValueError(f"Unknown {label}: {', '.join(invalid)}")


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
    plan: ResearchPlan | None = None
    agenda: ResearchAgenda | None = None
    section_briefs: dict[str, SectionResearchBrief] = Field(default_factory=dict)
    follow_up_done: bool = False
    ledger: SourceLedger = Field(default_factory=lambda: SourceLedger(entries=[]))
    verification: VerificationReport | None = None
    final_payload: CompendiumPayload | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_persisted_artifact_semantics(self) -> "ResearchRunState":
        for brief in self.section_briefs.values():
            validate_artifact_semantics(brief)
        validate_artifact_semantics(self.ledger)
        if self.verification is not None:
            validate_artifact_semantics(self.verification)
        return self

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
    "ResearchRunState",
    "prepare_compendium_payload",
    "validate_artifact_semantics",
]
