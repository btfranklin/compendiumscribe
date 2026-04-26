from __future__ import annotations

from compendiumscribe.research.pricing import resolve_model_pricing


def test_resolve_pricing_for_known_model() -> None:
    pricing = resolve_model_pricing("gpt-5.4")

    assert pricing is not None
    assert pricing.resolved_model == "gpt-5.4"
    assert pricing.input_per_1m_usd == 2.5
    assert pricing.cached_input_per_1m_usd == 0.25
    assert pricing.output_per_1m_usd == 15.0
    assert pricing.long_context_threshold_tokens == 272000
    assert pricing.long_context_input_per_1m_usd == 5.0
    assert pricing.long_context_output_per_1m_usd == 22.5
    assert pricing.tool_call_prices_per_1k_usd["web_search_call"] == 10.0
    assert pricing.tool_call_prices_per_1k_usd["file_search_call"] == 2.5


def test_unknown_model_returns_none() -> None:
    pricing = resolve_model_pricing("unknown-research-model")

    assert pricing is None
