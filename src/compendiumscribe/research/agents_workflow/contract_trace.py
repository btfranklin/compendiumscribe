from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    TraceAttemptClosure,
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

    def close(self) -> TraceClosureEvidence | None:
        if self._session_is_closed():
            return self._closure
        self.session.__exit__(None, None, None)
        candidate = self.session.closure_evidence
        prior_attempt_ids = {
            item.attempt.attempt_id
            for item in self._closure.attempts
        } if self._closure is not None else set()
        if any(
            item.attempt.attempt_id not in prior_attempt_ids
            for item in candidate.attempts
        ):
            closure = _merge_closure(self._closure, candidate)
            validate_trace_closure(self.trace, closure)
            self._persist_closure(closure)
            self._closure = closure
        return self._closure

    def emit(self, event: TraceEvent) -> None:
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
        self.session.emit(event)
        return event

    def _open_session(self) -> OpenAINormalizedTraceSession:
        session = _OPENAI_TRACE_ROUTER.open_session(
            self.ir,
            self.plan,
            run_id=self._context.run_id,
            thread_id=self._context.thread_id,
            sink=self.sink,
        )
        session.__enter__()
        try:
            if self._closure is not None:
                # v0.11 validates retry parents inside one session. Register
                # prior identities so a recovered retry can retain its durable
                # retry_of link; _merge_closure keeps the prior evidence.
                for item in self._closure.attempts:
                    with session.bind_attempt(item.attempt, agent=item.agent_id):
                        pass
        except BaseException as exc:
            session.__exit__(type(exc), exc, exc.__traceback__)
            raise
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
        atomic_write_text(self.closure_path, payload)

    def _session_is_closed(self) -> bool:
        try:
            self.session.closure_evidence
        except RuntimeError:
            return False
        return True


def _merge_closure(
    existing: TraceClosureEvidence | None,
    candidate: TraceClosureEvidence,
) -> TraceClosureEvidence:
    if existing is None:
        return candidate
    if existing.context != candidate.context:
        raise ValueError("Cannot merge trace closure from a different run context.")

    attempts: dict[str, TraceAttemptClosure] = {
        item.attempt.attempt_id: item for item in existing.attempts
    }
    for item in candidate.attempts:
        prior = attempts.get(item.attempt.attempt_id)
        if prior is None:
            attempts[item.attempt.attempt_id] = item
        elif prior.attempt != item.attempt or prior.agent_id != item.agent_id:
            raise ValueError(
                f"Trace closure attempt {item.attempt.attempt_id} changed identity."
            )

    ordered = tuple(sorted(attempts.values(), key=lambda item: item.attempt))
    if any(
        item.lifecycle_status == "incomplete"
        or item.response_status == "incomplete"
        for item in ordered
    ):
        status = "incomplete"
    elif any(not item.complete for item in ordered):
        status = "unverified"
    else:
        # The upstream session API cannot yet consume an earlier session's
        # closure as authoritative evidence. Cross-session recovery therefore
        # preserves every attempt identity without overstating aggregate
        # completeness.
        status = "unverified"
    channels = tuple(sorted(set(existing.channels) & set(candidate.channels)))
    return TraceClosureEvidence(
        context=existing.context,
        status=status,
        reason=(
            "Persisted closure combines all observed Contract4Agents trace "
            "sessions for this host-owned research run."
        ),
        channels=channels,
        attempts=ordered,
        evidence_refs=tuple(
            sorted(set(existing.evidence_refs) | set(candidate.evidence_refs))
        ),
    )


__all__ = ["ContractTraceRecorder"]
