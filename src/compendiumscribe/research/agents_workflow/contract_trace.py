from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import time

from contract4agents.ir import SemanticId, semantic_id
from contract4agents.tracing import (
    dumps_trace_jsonl,
    NormalizedTrace,
    ProviderCorrelation,
    TraceEvent,
    TraceRunContext,
    TraceSemanticRefs,
    load_trace_jsonl,
)

from .persistence import atomic_write_text


class ContractTraceRecorder:
    """Append host workflow evidence to one normalized Contract4Agents trace."""

    def __init__(
        self,
        path: Path,
        *,
        run_id: str,
        contract_digest: str,
        plan_digest: str,
        append: bool,
    ) -> None:
        self.path = path
        self.context = TraceRunContext(
            run_id=run_id,
            thread_id=run_id,
            contract_digest=contract_digest,
            plan_digest=plan_digest,
        )
        self.events: list[TraceEvent] = []
        if append and path.exists():
            existing = load_trace_jsonl(path)
            if any(event.context != self.context for event in existing.events):
                raise ValueError(
                    "Cannot resume a research trace with a different contract or "
                    "materialization plan."
                )
            self.events.extend(existing.events)

    @property
    def trace(self) -> NormalizedTrace:
        return NormalizedTrace(tuple(self.events))

    def record(
        self,
        event_type: str,
        *,
        agent_name: str | None = None,
        capability_name: str | None = None,
        control_ids: Sequence[SemanticId] = (),
        data: Mapping[str, object] | None = None,
        response_ids: Sequence[str] = (),
    ) -> TraceEvent:
        agent_id = semantic_id("agent", agent_name) if agent_name else None
        capability_id = (
            semantic_id("tool", capability_name) if capability_name else None
        )
        grant_id = (
            semantic_id("grant", agent_name, capability_name)
            if agent_name and capability_name
            else None
        )
        provider = ProviderCorrelation(
            "openai" if response_ids else "compendiumscribe",
            request_id=response_ids[0] if response_ids else None,
        )
        event = TraceEvent(
            context=self.context,
            event_id=f"{self.context.run_id}:{len(self.events) + 1:06d}",
            parent_event_id=None,
            event_type=event_type,
            timestamp=time.time(),
            semantic=TraceSemanticRefs(
                agent_id=agent_id,
                capability_id=capability_id,
                grant_id=grant_id,
                control_ids=tuple(control_ids),
            ),
            data=data or {},
            provider=provider,
            evidence_refs=tuple(response_ids),
            provenance={"recorder": "compendiumscribe"},
        )
        candidate = NormalizedTrace(tuple([*self.events, event]))
        atomic_write_text(self.path, dumps_trace_jsonl(candidate))
        self.events.append(event)
        return event


__all__ = ["ContractTraceRecorder"]
