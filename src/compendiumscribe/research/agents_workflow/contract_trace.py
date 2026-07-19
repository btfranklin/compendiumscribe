from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import time

from contract4agents.ir import CanonicalIR, SemanticId, semantic_id
from contract4agents.planning import MaterializationPlan
from contract4agents.tracing import (
    AtomicTraceFileSink,
    NormalizedTrace,
    OpenAINormalizedTraceProcessor,
    ProviderCorrelation,
    TraceAttempt,
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
        ir: CanonicalIR,
        plan: MaterializationPlan,
        append: bool,
    ) -> None:
        from agents import add_trace_processor

        context = TraceRunContext(
            run_id=run_id,
            thread_id=run_id,
            contract_digest=plan.contract_digest,
            plan_digest=plan.plan_digest,
        )
        self.sink = AtomicTraceFileSink(path, context, append=append)
        self.processor = OpenAINormalizedTraceProcessor(
            ir,
            plan,
            run_id=run_id,
            thread_id=run_id,
            sink=self.sink,
        )
        add_trace_processor(self.processor)

    @property
    def context(self) -> TraceRunContext:
        return self.processor.context

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return self.sink.events

    @property
    def trace(self) -> NormalizedTrace:
        return self.sink.normalized_trace()

    def emit(self, event: TraceEvent) -> None:
        self.processor.emit(event)

    def bind_attempt(self, attempt: TraceAttempt):
        return self.processor.bind_attempt(attempt)

    def normalize_response_events(
        self,
        responses: Sequence[object],
        *,
        agent_name: str,
        attempt: TraceAttempt,
    ) -> tuple[TraceEvent, ...]:
        return self.processor.normalize_response_events(
            responses,
            agent=agent_name,
            attempt=attempt,
        )

    def normalize_exception_responses(
        self,
        exception: BaseException,
        *,
        agent_name: str,
        attempt: TraceAttempt,
    ) -> tuple[TraceEvent, ...]:
        return self.processor.normalize_exception_responses(
            exception,
            agent=agent_name,
            attempt=attempt,
        )

    def record_output_schema_failure(
        self,
        *,
        agent_name: str,
        attempt: TraceAttempt,
        evidence_refs: Sequence[str] = (),
    ) -> TraceEvent:
        return self.processor.record_output_schema_failure(
            agent=agent_name,
            attempt=attempt,
            evidence_refs=tuple(evidence_refs),
        )

    def record_terminal_attempt(
        self,
        *,
        agent_name: str,
        attempt: TraceAttempt,
        outcome: str,
        evidence_refs: Sequence[str] = (),
    ) -> TraceEvent:
        if outcome not in {"succeeded", "failed"}:
            raise ValueError(f"Unsupported terminal attempt outcome: {outcome}")
        return self.processor.record_terminal_attempt(
            agent=agent_name,
            attempt=attempt,
            outcome=outcome,
            evidence_refs=tuple(evidence_refs),
        )

    def record(
        self,
        event_type: str,
        *,
        agent_name: str | None = None,
        control_ids: Sequence[SemanticId] = (),
        data: Mapping[str, object] | None = None,
        response_ids: Sequence[str] = (),
        attempt: TraceAttempt | None = None,
    ) -> TraceEvent:
        agent_id = semantic_id("agent", agent_name) if agent_name else None
        provider = ProviderCorrelation(
            "openai" if response_ids else "compendiumscribe",
            request_id=response_ids[0] if response_ids else None,
        )
        event_data = dict(data or {})
        if attempt is not None:
            event_data["attempt"] = attempt.to_dict()
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
            data=event_data,
            provider=provider,
            evidence_refs=tuple(response_ids),
            provenance={"recorder": "compendiumscribe"},
        )
        self.processor.emit(event)
        return event


__all__ = ["ContractTraceRecorder"]
