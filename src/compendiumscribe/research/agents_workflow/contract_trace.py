from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import time

from contract4agents.ir import SemanticId, semantic_id
from contract4agents.tracing import (
    AtomicTraceFileSink,
    NormalizedTrace,
    ProviderCorrelation,
    TraceEvent,
    TraceRunContext,
    TraceSemanticRefs,
)


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
        self.context = TraceRunContext(
            run_id=run_id,
            thread_id=run_id,
            contract_digest=contract_digest,
            plan_digest=plan_digest,
        )
        self.sink = AtomicTraceFileSink(path, self.context, append=append)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return self.sink.events

    @property
    def trace(self) -> NormalizedTrace:
        return self.sink.normalized_trace()

    def emit(self, event: TraceEvent) -> None:
        self.sink.emit(event)

    def record(
        self,
        event_type: str,
        *,
        agent_name: str | None = None,
        control_ids: Sequence[SemanticId] = (),
        data: Mapping[str, object] | None = None,
        response_ids: Sequence[str] = (),
    ) -> TraceEvent:
        agent_id = semantic_id("agent", agent_name) if agent_name else None
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
                control_ids=tuple(control_ids),
            ),
            data=data or {},
            provider=provider,
            evidence_refs=tuple(response_ids),
            provenance={"recorder": "compendiumscribe"},
        )
        self.sink.emit(event)
        return event


__all__ = ["ContractTraceRecorder"]
