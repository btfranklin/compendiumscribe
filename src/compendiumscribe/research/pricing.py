from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import json

from .costs import CostPricing


CATALOG_PATH = Path(__file__).resolve().parent / "data" / "pricing.standard.json"


@dataclass(frozen=True)
class ModelPricing:
    requested_model: str
    resolved_model: str
    tier: str
    source_url: str
    as_of_utc: str
    input_per_1m_usd: float
    cached_input_per_1m_usd: float | None
    output_per_1m_usd: float
    long_context_input_per_1m_usd: float | None = None
    long_context_cached_input_per_1m_usd: float | None = None
    long_context_output_per_1m_usd: float | None = None
    long_context_threshold_tokens: int | None = None
    tool_call_prices_per_1k_usd: dict[str, float] = field(default_factory=dict)

    def to_cost_pricing(self) -> CostPricing:
        return CostPricing(
            input_per_1m_usd=self.input_per_1m_usd,
            output_per_1m_usd=self.output_per_1m_usd,
            cached_input_per_1m_usd=self.cached_input_per_1m_usd,
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


@lru_cache(maxsize=4)
def _load_catalog(catalog_path: str) -> dict:
    with Path(catalog_path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Pricing catalog must be a JSON object")
    return data


def resolve_model_pricing(
    model: str,
    *,
    catalog_path: Path | None = None,
) -> ModelPricing | None:
    normalized_model = model.strip().lower()
    if not normalized_model:
        return None

    resolved_catalog_path = catalog_path or CATALOG_PATH
    catalog = _load_catalog(str(resolved_catalog_path))
    models = catalog.get("models", {})
    if not isinstance(models, dict):
        return None

    raw_pricing = models.get(normalized_model)
    if not isinstance(raw_pricing, dict):
        return None

    try:
        input_rate = float(raw_pricing["input_per_1m_usd"])
        cached_input_rate = _optional_float(
            raw_pricing.get("cached_input_per_1m_usd")
        )
        output_rate = float(raw_pricing["output_per_1m_usd"])
    except (KeyError, TypeError, ValueError):
        return None
    long_context = raw_pricing.get("long_context")
    long_context_threshold_tokens: int | None = None
    long_context_input_rate: float | None = None
    long_context_cached_input_rate: float | None = None
    long_context_output_rate: float | None = None
    if isinstance(long_context, dict):
        long_context_threshold_tokens = _optional_int(
            long_context.get("threshold_tokens")
        )
        long_context_input_rate = _optional_float(
            long_context.get("input_per_1m_usd")
        )
        long_context_cached_input_rate = _optional_float(
            long_context.get("cached_input_per_1m_usd")
        )
        long_context_output_rate = _optional_float(
            long_context.get("output_per_1m_usd")
        )

    raw_tool_pricing = catalog.get("tool_call_prices_per_1k_usd", {})
    tool_call_prices_per_1k_usd: dict[str, float] = {}
    if isinstance(raw_tool_pricing, dict):
        for tool_name, tool_price in raw_tool_pricing.items():
            if not isinstance(tool_name, str):
                continue
            try:
                tool_call_prices_per_1k_usd[tool_name] = float(tool_price)
            except (TypeError, ValueError):
                continue

    return ModelPricing(
        requested_model=normalized_model,
        resolved_model=normalized_model,
        tier=str(catalog.get("tier", "unknown")),
        source_url=str(catalog.get("source_url", "")),
        as_of_utc=str(catalog.get("as_of_utc", "")),
        input_per_1m_usd=input_rate,
        cached_input_per_1m_usd=cached_input_rate,
        output_per_1m_usd=output_rate,
        long_context_input_per_1m_usd=long_context_input_rate,
        long_context_cached_input_per_1m_usd=long_context_cached_input_rate,
        long_context_output_per_1m_usd=long_context_output_rate,
        long_context_threshold_tokens=long_context_threshold_tokens,
        tool_call_prices_per_1k_usd=tool_call_prices_per_1k_usd,
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


__all__ = [
    "CATALOG_PATH",
    "ModelPricing",
    "resolve_model_pricing",
]
