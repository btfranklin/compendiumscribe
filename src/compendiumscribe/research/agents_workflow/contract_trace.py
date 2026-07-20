from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
import time

from agents import add_trace_processor
from contract4agents.ir import CanonicalIR, SemanticId, semantic_id
from contract4agents.planning import MaterializationPlan
from contract4agents.tracing import (
    AtomicTraceFileSink,
    NormalizedTrace,
    OpenAINormalizedTraceRouter,
    OpenAINormalizedTraceSession,
    ProviderCorrelation,
    TraceAttempt,
    TraceCaptureSnapshot,
    TraceClosureEvidence,
    TraceClosureManifest,
    TraceEvent,
    TraceRunContext,
    TraceSemanticRefs,
    validate_trace_closure,
)

from .persistence import atomic_write_text


_OPENAI_TRACE_ROUTER = OpenAINormalizedTraceRouter()
add_trace_processor(_OPENAI_TRACE_ROUTER)


class ContractTraceRecorder:
    """Append one run's normalized trace and persist its closure evidence."""

    def __init__(
        self,
        path: Path,
        closure_path: Path,
        *,
        run_id: str,
        ir: CanonicalIR,
        plan: MaterializationPlan,
        append: bool,
    ) -> None:
        self.ir = ir
        self.plan = plan
        self.closure_path = closure_path
        context = TraceRunContext(
            run_id=run_id,
            thread_id=run_id,
            contract_digest=plan.contract_digest,
            plan_digest=plan.plan_digest,
        )
        self._context = context
        self._capture_write_failed = False
        self.sink = AtomicTraceFileSink(path, context, append=append)
        self._closure = self._load_closure(context) if append else None
        if self._closure is not None:
            validate_trace_closure(self.trace, self._closure)
        self.session = self._open_session()

    @property
    def context(self) -> TraceRunContext:
        return self._context

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return self.sink.events

    @property
    def trace(self) -> NormalizedTrace:
        return self.sink.normalized_trace()

    @property
    def closure(self) -> TraceClosureEvidence | None:
        return self._closure

    def checkpoint(self) -> TraceCaptureSnapshot:
        self._ensure_capture_writable()
        snapshot = self.session.snapshot()
        self._persist_snapshot(snapshot)
        return snapshot

    def close(self) -> TraceCaptureSnapshot:
        if self._session_is_closed():
            return self.session.closed_snapshot
        try:
            self.session.__exit__(None, None, None)
        except OSError:
            self._capture_write_failed = True
            raise
        snapshot = self.session.closed_snapshot
        if self._capture_write_failed:
            return snapshot
        self._persist_snapshot(snapshot)
        return snapshot

    def emit(self, event: TraceEvent) -> None:
        with self._capture_write():
            self.session.emit(event)

    def bind_attempt(self, attempt: TraceAttempt, *, agent_name: str):
        return self.session.bind_attempt(attempt, agent=agent_name)

    def normalize_response_events(
        self,
        responses: Sequence[object],
        *,
        agent_name: str,
        attempt: TraceAttempt,
    ) -> tuple[TraceEvent, ...]:
        with self._capture_write():
            return self.session.normalize_response_events(
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
        with self._capture_write():
            return self.session.normalize_exception_responses(
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
        with self._capture_write():
            return self.session.record_output_schema_failure(
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
        with self._capture_write():
            return self.session.record_terminal_attempt(
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
        with self._capture_write():
            self.session.emit(event)
        return event

    def _open_session(self) -> OpenAINormalizedTraceSession:
        session = _OPENAI_TRACE_ROUTER.open_session(
            self.ir,
            self.plan,
            run_id=self._context.run_id,
            thread_id=self._context.thread_id,
            sink=self.sink,
            prior_trace=self.trace if self._closure is not None else None,
            prior_closure=self._closure,
        )
        session.__enter__()
        return session

    def _load_closure(
        self,
        context: TraceRunContext,
    ) -> TraceClosureEvidence | None:
        if not self.closure_path.exists():
            return None
        manifest = TraceClosureManifest.load(self.closure_path)
        matches = [
            item for item in manifest.closures if item.context.run_id == context.run_id
        ]
        if len(matches) != 1 or len(manifest.closures) != 1:
            raise ValueError(
                "Trace-closure manifest must contain exactly one matching run."
            )
        closure = matches[0]
        if closure.context != context:
            raise ValueError(
                "Trace-closure evidence does not match the current run context."
            )
        return closure

    def _persist_closure(self, closure: TraceClosureEvidence) -> None:
        payload = TraceClosureManifest((closure,)).to_json() + "\n"
        try:
            atomic_write_text(self.closure_path, payload)
        except OSError:
            self._capture_write_failed = True
            raise
        self._closure = closure

    def _persist_snapshot(self, snapshot: TraceCaptureSnapshot) -> None:
        if snapshot.trace != self.trace:
            raise ValueError(
                "Contract4Agents capture snapshot does not match the persisted trace."
            )
        if snapshot.closure != self._closure:
            self._persist_closure(snapshot.closure)

    def _session_is_closed(self) -> bool:
        try:
            self.session.closed_snapshot
        except RuntimeError:
            return False
        return True

    def _ensure_capture_writable(self) -> None:
        if self._capture_write_failed:
            raise RuntimeError(
                "Contract4Agents capture cannot continue after a persistence failure."
            )

    @contextmanager
    def _capture_write(self):
        self._ensure_capture_writable()
        try:
            yield
        except OSError:
            self._capture_write_failed = True
            raise


__all__ = ["ContractTraceRecorder"]
