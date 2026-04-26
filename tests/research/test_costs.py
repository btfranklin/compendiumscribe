from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from compendiumscribe.research.costs import (
    COSTS_SCHEMA_VERSION,
    CostPricing,
    CostTracker,
    TokenUsage,
    estimate_step_cost_usd,
    estimate_tool_call_cost_usd,
    extract_tool_calls_from_response,
    extract_usage_from_response,
)


def test_estimate_step_cost_uses_cached_and_uncached_rates() -> None:
    usage = TokenUsage(
        input_tokens=1_000_000,
        cached_input_tokens=200_000,
        output_tokens=100_000,
        reasoning_tokens=50_000,
    )
    pricing = CostPricing(
        input_per_1m_usd=2.0,
        cached_input_per_1m_usd=0.5,
        output_per_1m_usd=8.0,
    )

    estimated = estimate_step_cost_usd(usage, pricing)

    assert estimated is not None
    assert round(estimated, 6) == round(1.6 + 0.1 + 0.8, 6)


def test_estimate_tool_call_cost_uses_per_1k_rate() -> None:
    pricing = CostPricing(
        input_per_1m_usd=None,
        cached_input_per_1m_usd=None,
        output_per_1m_usd=None,
        tool_call_prices_per_1k_usd={"web_search_call": 10.0},
    )

    estimated = estimate_tool_call_cost_usd({"web_search_call": 3}, pricing)

    assert round(estimated, 6) == round(0.03, 6)


def test_estimate_step_cost_uses_long_context_rates() -> None:
    usage = TokenUsage(
        input_tokens=300_000,
        cached_input_tokens=100_000,
        output_tokens=50_000,
    )
    pricing = CostPricing(
        input_per_1m_usd=2.5,
        cached_input_per_1m_usd=0.25,
        output_per_1m_usd=15.0,
        long_context_threshold_tokens=272_000,
        long_context_input_per_1m_usd=5.0,
        long_context_cached_input_per_1m_usd=0.5,
        long_context_output_per_1m_usd=22.5,
    )

    estimated = estimate_step_cost_usd(usage, pricing)

    assert estimated is not None
    assert round(estimated, 6) == round(1.0 + 0.05 + 1.125, 6)


def test_extract_usage_from_response_reads_cached_and_reasoning() -> None:
    response = {
        "usage": {
            "input_tokens": 120,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens": 42,
            "output_tokens_details": {"reasoning_tokens": 7},
        }
    }

    usage = extract_usage_from_response(response)

    assert usage is not None
    assert usage.input_tokens == 120
    assert usage.cached_input_tokens == 20
    assert usage.output_tokens == 42
    assert usage.reasoning_tokens == 7


def test_extract_tool_calls_from_response_counts_call_items() -> None:
    response = {
        "output": [
            {"type": "web_search_call"},
            {"type": "web_search_call"},
            {"type": "message"},
            {"type": "function_call"},
        ]
    }

    tool_calls = extract_tool_calls_from_response(response)

    assert tool_calls == {"web_search_call": 2, "function_call": 1}


def test_cost_tracker_persists_steps_and_totals(tmp_path: Path) -> None:
    path = tmp_path / "costs.json"
    pricing = CostPricing(
        input_per_1m_usd=1.0,
        cached_input_per_1m_usd=0.5,
        output_per_1m_usd=2.0,
        tool_call_prices_per_1k_usd={"web_search_call": 10.0},
    )
    tracker = CostTracker(path=path, pricing=pricing)

    first = tracker.record_step(
        phase="planning",
        request_id="resp_1",
        model="gpt-5.2",
        usage=TokenUsage(
            input_tokens=100_000,
            cached_input_tokens=20_000,
            output_tokens=30_000,
        ),
        tool_calls={"web_search_call": 2},
    )
    assert first is not None

    tracker = CostTracker(path=path, pricing=pricing)
    second = tracker.record_step(
        phase="section_research",
        request_id="resp_2",
        model="gpt-5.2",
        usage=TokenUsage(
            input_tokens=50_000,
            cached_input_tokens=0,
            output_tokens=10_000,
        ),
        tool_calls={"web_search_call": 1},
    )
    assert second is not None
    assert second.running_total_usd > first.running_total_usd

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == COSTS_SCHEMA_VERSION
    assert len(payload["steps"]) == 2
    assert payload["totals"]["tool_calls"]["web_search_call"] == 3


def test_cost_tracker_records_applied_long_context_rate(tmp_path: Path) -> None:
    path = tmp_path / "costs.json"
    tracker = CostTracker(
        path=path,
        pricing=CostPricing(
            input_per_1m_usd=2.5,
            cached_input_per_1m_usd=0.25,
            output_per_1m_usd=15.0,
            long_context_threshold_tokens=272_000,
            long_context_input_per_1m_usd=5.0,
            long_context_cached_input_per_1m_usd=0.5,
            long_context_output_per_1m_usd=22.5,
        ),
    )

    tracker.record_step(
        phase="section_research",
        request_id="resp_long",
        model="gpt-5.4",
        usage=TokenUsage(input_tokens=300_000, output_tokens=1_000),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["steps"][0]["pricing"]["input_per_1m_usd"] == 5.0
    assert payload["steps"][0]["pricing"]["output_per_1m_usd"] == 22.5


def test_cost_tracker_record_response_uses_model_resolver(tmp_path: Path) -> None:
    path = tmp_path / "costs.json"
    unknown_pricing = CostPricing(
        input_per_1m_usd=None,
        cached_input_per_1m_usd=None,
        output_per_1m_usd=None,
        requested_model="unknown-model",
    )
    resolved_pricing = CostPricing(
        input_per_1m_usd=2.0,
        cached_input_per_1m_usd=0.5,
        output_per_1m_usd=8.0,
        requested_model="gpt-5.2",
        resolved_model="gpt-5.2",
    )

    def resolver(model: str) -> CostPricing | None:
        if model == "gpt-5.2":
            return resolved_pricing
        return None

    tracker = CostTracker(
        path=path,
        pricing=unknown_pricing,
        pricing_resolver=resolver,
    )

    response = SimpleNamespace(
        id="resp_123",
        model="gpt-5.2",
        usage={
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 10,
            "output_tokens_details": {"reasoning_tokens": 0},
        },
        output=[{"type": "web_search_call"}],
    )

    step = tracker.record_response(phase="section_research", response=response)

    assert step is not None
    assert step.estimated_cost_usd is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["steps"][0]["pricing"]["resolved_model"] == "gpt-5.2"
