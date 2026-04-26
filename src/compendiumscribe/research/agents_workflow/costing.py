from __future__ import annotations

from typing import Any

from ..costs import (
    CostTracker,
    TokenUsage,
    extract_tool_calls_from_response,
    extract_usage_from_response,
)


def record_agent_result_cost(
    cost_tracker: CostTracker | None,
    *,
    phase: str,
    model: str | None,
    result: Any,
) -> None:
    if cost_tracker is None:
        return

    raw_result = getattr(result, "raw_result", result)
    responses = list(getattr(raw_result, "raw_responses", []) or [])
    if not responses:
        return

    usage = _aggregate_usage(responses)
    tool_calls = _aggregate_tool_calls(responses)
    response_ids = [
        str(response_id)
        for response_id in (
            getattr(response, "response_id", None)
            or getattr(response, "id", None)
            for response in responses
        )
        if response_id
    ]
    request_id = ",".join(response_ids) if response_ids else None
    pricing = cost_tracker.resolve_pricing_for_model(model)

    try:
        cost_tracker.record_step(
            phase=phase,
            request_id=request_id,
            model=model,
            usage=usage,
            tool_calls=tool_calls,
            pricing=pricing,
        )
    except Exception:
        return


def _aggregate_usage(responses: list[Any]) -> TokenUsage | None:
    usages = [
        usage
        for response in responses
        if (usage := extract_usage_from_response(response)) is not None
    ]
    if not usages:
        return None
    return TokenUsage(
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        cached_input_tokens=sum(
            usage.cached_input_tokens for usage in usages
        ),
        reasoning_tokens=sum(usage.reasoning_tokens for usage in usages),
    )


def _aggregate_tool_calls(responses: list[Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for response in responses:
        for name, count in extract_tool_calls_from_response(response).items():
            totals[name] = totals.get(name, 0) + count
    return totals


__all__ = ["record_agent_result_cost"]
