from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json

from .utils import coerce_optional_string, get_field


ONE_MILLION = 1_000_000
COSTS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass(frozen=True)
class CostPricing:
    input_per_1m_usd: float | None
    output_per_1m_usd: float | None
    cached_input_per_1m_usd: float | None
    long_context_input_per_1m_usd: float | None = None
    long_context_cached_input_per_1m_usd: float | None = None
    long_context_output_per_1m_usd: float | None = None
    long_context_threshold_tokens: int | None = None
    tool_call_prices_per_1k_usd: dict[str, float] = field(default_factory=dict)
    requested_model: str | None = None
    resolved_model: str | None = None
    tier: str | None = None
    source_url: str | None = None
    as_of_utc: str | None = None

    @property
    def token_pricing_configured(self) -> bool:
        return self.input_per_1m_usd is not None and self.output_per_1m_usd is not None

    @property
    def tool_pricing_configured(self) -> bool:
        return bool(self.tool_call_prices_per_1k_usd)

    @property
    def configured(self) -> bool:
        return self.token_pricing_configured or self.tool_pricing_configured

    @property
    def effective_cached_input_per_1m_usd(self) -> float | None:
        if self.cached_input_per_1m_usd is not None:
            return self.cached_input_per_1m_usd
        return self.input_per_1m_usd

    def rate_card_for_usage(self, usage: TokenUsage) -> "CostPricing":
        threshold = self.long_context_threshold_tokens
        if threshold is None or usage.input_tokens <= threshold:
            return self
        return CostPricing(
            input_per_1m_usd=(
                self.long_context_input_per_1m_usd
                if self.long_context_input_per_1m_usd is not None
                else self.input_per_1m_usd
            ),
            cached_input_per_1m_usd=(
                self.long_context_cached_input_per_1m_usd
                if self.long_context_cached_input_per_1m_usd is not None
                else self.cached_input_per_1m_usd
            ),
            output_per_1m_usd=(
                self.long_context_output_per_1m_usd
                if self.long_context_output_per_1m_usd is not None
                else self.output_per_1m_usd
            ),
            long_context_input_per_1m_usd=self.long_context_input_per_1m_usd,
            long_context_cached_input_per_1m_usd=(
                self.long_context_cached_input_per_1m_usd
            ),
            long_context_output_per_1m_usd=self.long_context_output_per_1m_usd,
            long_context_threshold_tokens=self.long_context_threshold_tokens,
            tool_call_prices_per_1k_usd=self.tool_call_prices_per_1k_usd,
            requested_model=self.requested_model,
            resolved_model=self.resolved_model,
            tier=self.tier,
            source_url=self.source_url,
            as_of_utc=self.as_of_utc,
        )


@dataclass(frozen=True)
class StepCost:
    estimated_cost_usd: float | None
    estimated_token_cost_usd: float | None
    estimated_tool_cost_usd: float
    running_total_usd: float


def estimate_step_cost_usd(usage: TokenUsage, pricing: CostPricing) -> float | None:
    active_pricing = pricing.rate_card_for_usage(usage)
    if not active_pricing.token_pricing_configured:
        return None

    input_rate = active_pricing.input_per_1m_usd
    output_rate = active_pricing.output_per_1m_usd
    cached_input_rate = active_pricing.effective_cached_input_per_1m_usd
    if input_rate is None or output_rate is None or cached_input_rate is None:
        return None

    cached_tokens = max(usage.cached_input_tokens, 0)
    uncached_input_tokens = max(usage.input_tokens - cached_tokens, 0)
    input_cost = (uncached_input_tokens / ONE_MILLION) * input_rate
    cached_input_cost = (cached_tokens / ONE_MILLION) * cached_input_rate
    output_cost = (usage.output_tokens / ONE_MILLION) * output_rate
    return input_cost + cached_input_cost + output_cost


def estimate_tool_call_cost_usd(
    tool_calls: dict[str, int], pricing: CostPricing
) -> float:
    total = 0.0
    for tool_name, count in tool_calls.items():
        price_per_1k = pricing.tool_call_prices_per_1k_usd.get(tool_name)
        if price_per_1k is None:
            continue
        safe_count = max(int(count), 0)
        total += (safe_count / 1000) * float(price_per_1k)
    return total


def extract_usage_from_response(response: Any) -> TokenUsage | None:
    usage = get_field(response, "usage")
    if usage is None:
        return None

    input_details = get_field(usage, "input_tokens_details")
    output_details = get_field(usage, "output_tokens_details")

    cached_tokens = _int_like(
        get_field(input_details, "cached_tokens")
        if input_details is not None
        else 0
    )
    if cached_tokens == 0:
        cached_tokens = _int_like(
            get_field(input_details, "cached_input_tokens")
            if input_details is not None
            else 0
        )

    return TokenUsage(
        input_tokens=_int_like(get_field(usage, "input_tokens")),
        cached_input_tokens=cached_tokens,
        output_tokens=_int_like(get_field(usage, "output_tokens")),
        reasoning_tokens=_int_like(
            get_field(output_details, "reasoning_tokens")
            if output_details is not None
            else 0
        ),
    )


def extract_tool_calls_from_response(response: Any) -> dict[str, int]:
    output_items = get_field(response, "output")
    if not isinstance(output_items, list):
        return {}

    counts: dict[str, int] = {}
    for item in output_items:
        item_type = coerce_optional_string(get_field(item, "type"))
        if item_type is None or not item_type.endswith("_call"):
            continue
        counts[item_type] = counts.get(item_type, 0) + 1
    return counts


class CostTracker:
    def __init__(
        self,
        *,
        path: Path,
        pricing: CostPricing,
        pricing_resolver: Callable[[str], CostPricing | None] | None = None,
    ) -> None:
        self.path = path
        self.pricing = pricing
        self._pricing_resolver = pricing_resolver
        self._running_total_usd = 0.0
        self._load_running_total()

    @property
    def running_total_usd(self) -> float:
        return self._running_total_usd

    @property
    def step_count(self) -> int:
        payload = self._read_payload()
        steps = payload.get("steps")
        if isinstance(steps, list):
            return len(steps)
        return 0

    def initialize_report(self) -> None:
        if not self.path.exists():
            payload = self._default_payload()
            payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
            payload["default_pricing"] = self._pricing_payload(self.pricing)
            payload["totals"] = self._summarize_steps(
                steps=[],
                running_total_usd=self._running_total_usd,
            )
            self._write_payload(payload)

    def resolve_pricing_for_model(self, model: str | None) -> CostPricing:
        if model is None or self._pricing_resolver is None:
            return self.pricing
        resolved = self._pricing_resolver(model)
        if resolved is None:
            return self.pricing
        return resolved

    def record_response(
        self,
        *,
        phase: str,
        response: Any,
        pricing: CostPricing | None = None,
    ) -> StepCost | None:
        usage = extract_usage_from_response(response)
        tool_calls = extract_tool_calls_from_response(response)
        request_id = coerce_optional_string(get_field(response, "id"))
        model = coerce_optional_string(get_field(response, "model"))
        active_pricing = pricing or self.resolve_pricing_for_model(model)
        return self.record_step(
            phase=phase,
            request_id=request_id,
            model=model,
            usage=usage,
            tool_calls=tool_calls,
            pricing=active_pricing,
        )

    def record_step(
        self,
        *,
        phase: str,
        request_id: str | None,
        usage: TokenUsage | None,
        tool_calls: dict[str, int] | None = None,
        model: str | None = None,
        pricing: CostPricing | None = None,
    ) -> StepCost | None:
        normalized_tool_calls: dict[str, int] = {}
        for name, count in (tool_calls or {}).items():
            if not isinstance(name, str):
                continue
            try:
                safe_count = max(int(count), 0)
            except (TypeError, ValueError):
                continue
            normalized_tool_calls[name] = safe_count

        if usage is None and not normalized_tool_calls:
            return None

        active_pricing = pricing or self.pricing
        applied_pricing = (
            active_pricing.rate_card_for_usage(usage)
            if usage is not None
            else active_pricing
        )
        token_cost = (
            estimate_step_cost_usd(usage, active_pricing)
            if usage is not None
            else None
        )
        tool_cost = estimate_tool_call_cost_usd(
            normalized_tool_calls, active_pricing
        )

        if token_cost is None and tool_cost == 0:
            step_cost = None
        elif token_cost is None:
            step_cost = tool_cost
        else:
            step_cost = token_cost + tool_cost

        if step_cost is not None:
            self._running_total_usd += step_cost

        payload = self._read_payload()
        steps = payload.get("steps")
        if not isinstance(steps, list):
            steps = []

        steps.append(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "phase": phase,
                "request_id": request_id,
                "model": model,
                "pricing": self._pricing_payload(applied_pricing),
                "usage": {
                    "input_tokens": 0 if usage is None else usage.input_tokens,
                    "cached_input_tokens": (
                        0 if usage is None else usage.cached_input_tokens
                    ),
                    "output_tokens": 0 if usage is None else usage.output_tokens,
                    "reasoning_tokens": (
                        0 if usage is None else usage.reasoning_tokens
                    ),
                },
                "tool_calls": normalized_tool_calls,
                "estimated_token_cost_usd": token_cost,
                "estimated_tool_cost_usd": tool_cost,
                "estimated_cost_usd": step_cost,
                "running_total_usd": self._running_total_usd,
            }
        )

        payload["schema_version"] = COSTS_SCHEMA_VERSION
        if not payload.get("generated_at_utc"):
            payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        payload["default_pricing"] = self._pricing_payload(self.pricing)
        payload["steps"] = steps
        payload["totals"] = self._summarize_steps(
            steps=steps,
            running_total_usd=self._running_total_usd,
        )
        self._write_payload(payload)

        return StepCost(
            estimated_cost_usd=step_cost,
            estimated_token_cost_usd=token_cost,
            estimated_tool_cost_usd=tool_cost,
            running_total_usd=self._running_total_usd,
        )

    def totals_snapshot(self) -> dict[str, Any]:
        payload = self._read_payload()
        totals = payload.get("totals")
        if not isinstance(totals, dict):
            return {
                "estimated_cost_usd": 0.0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "tool_calls": {},
            }
        return totals

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._default_payload()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self._default_payload()
        if not isinstance(data, dict):
            return self._default_payload()
        return data

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def _default_payload(self) -> dict[str, Any]:
        return {"schema_version": COSTS_SCHEMA_VERSION, "steps": []}

    def _load_running_total(self) -> None:
        payload = self._read_payload()
        totals = payload.get("totals")
        if not isinstance(totals, dict):
            return
        try:
            estimated_cost = totals.get("estimated_cost_usd", 0.0)
            self._running_total_usd = float(estimated_cost)
        except (TypeError, ValueError):
            self._running_total_usd = 0.0

    def _summarize_steps(
        self,
        *,
        steps: list[dict[str, Any]],
        running_total_usd: float,
    ) -> dict[str, Any]:
        input_tokens = 0
        cached_input_tokens = 0
        output_tokens = 0
        reasoning_tokens = 0
        tool_calls: dict[str, int] = {}

        for step in steps:
            usage = step.get("usage")
            if isinstance(usage, dict):
                input_tokens += _int_like(usage.get("input_tokens"))
                cached_input_tokens += _int_like(
                    usage.get("cached_input_tokens")
                )
                output_tokens += _int_like(usage.get("output_tokens"))
                reasoning_tokens += _int_like(usage.get("reasoning_tokens"))

            step_tool_calls = step.get("tool_calls")
            if isinstance(step_tool_calls, dict):
                for tool_name, raw_count in step_tool_calls.items():
                    if not isinstance(tool_name, str):
                        continue
                    tool_calls[tool_name] = tool_calls.get(tool_name, 0) + _int_like(
                        raw_count
                    )

        return {
            "estimated_cost_usd": running_total_usd,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "tool_calls": tool_calls,
        }

    @staticmethod
    def _pricing_payload(pricing: CostPricing) -> dict[str, Any]:
        return {
            "requested_model": pricing.requested_model,
            "resolved_model": pricing.resolved_model,
            "tier": pricing.tier,
            "source_url": pricing.source_url,
            "as_of_utc": pricing.as_of_utc,
            "input_per_1m_usd": pricing.input_per_1m_usd,
            "cached_input_per_1m_usd": pricing.effective_cached_input_per_1m_usd,
            "output_per_1m_usd": pricing.output_per_1m_usd,
            "long_context_threshold_tokens": (
                pricing.long_context_threshold_tokens
            ),
            "long_context_input_per_1m_usd": (
                pricing.long_context_input_per_1m_usd
            ),
            "long_context_cached_input_per_1m_usd": (
                pricing.long_context_cached_input_per_1m_usd
            ),
            "long_context_output_per_1m_usd": (
                pricing.long_context_output_per_1m_usd
            ),
            "tool_call_prices_per_1k_usd": pricing.tool_call_prices_per_1k_usd,
            "configured": pricing.configured,
        }


def record_response_cost(
    cost_tracker: CostTracker | None,
    *,
    phase: str,
    response: Any,
) -> StepCost | None:
    if cost_tracker is None:
        return None
    try:
        return cost_tracker.record_response(phase=phase, response=response)
    except Exception:
        # Cost tracking should never break the core research workflow.
        return None


def _int_like(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "COSTS_SCHEMA_VERSION",
    "CostPricing",
    "CostTracker",
    "StepCost",
    "TokenUsage",
    "estimate_step_cost_usd",
    "estimate_tool_call_cost_usd",
    "extract_tool_calls_from_response",
    "extract_usage_from_response",
    "record_response_cost",
]
