from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
import warnings
import json

from .costs import CostPricing


CATALOG_PATH = Path(__file__).resolve().parent / "data" / "pricing.standard.json"
PRICING_MAX_AGE_DAYS = 90


class PricingCatalogWarning(UserWarning):
    """Warn that pricing estimates use missing, invalid, or old rates."""


_catalog_warning_lock = Lock()
_catalog_freshness_checked = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ModelPricing:
    requested_model: str
    resolved_model: str
    tier: str
    source_url: str
    last_updated_utc: str
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
            last_updated_utc=self.last_updated_utc,
        )


@lru_cache(maxsize=4)
def _load_catalog(catalog_path: str) -> dict:
    with Path(catalog_path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Pricing catalog must be a JSON object")
    return data


def _warn_if_catalog_is_not_current(
    catalog: dict,
    *,
    now_utc: datetime | None = None,
) -> None:
    global _catalog_freshness_checked

    with _catalog_warning_lock:
        if _catalog_freshness_checked:
            return
        _catalog_freshness_checked = True

    raw_timestamp = catalog.get("last_updated_utc")
    if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
        _warn_about_pricing_catalog(
            "The pricing catalog has no last_updated_utc timestamp. "
            "Cost estimates can use old rates."
        )
        return

    try:
        parsed_timestamp = datetime.fromisoformat(
            raw_timestamp.strip().replace("Z", "+00:00")
        )
    except ValueError:
        _warn_about_pricing_catalog(
            "The pricing catalog has an invalid last_updated_utc timestamp. "
            "Cost estimates can use old rates."
        )
        return

    if (
        parsed_timestamp.tzinfo is None
        or parsed_timestamp.utcoffset() != timedelta(0)
    ):
        _warn_about_pricing_catalog(
            "The pricing catalog has an invalid last_updated_utc timestamp. "
            "The timestamp must use UTC. Cost estimates can use old rates."
        )
        return

    current_time = now_utc or _utc_now()
    age = current_time.astimezone(timezone.utc) - parsed_timestamp.astimezone(
        timezone.utc
    )
    if age > timedelta(days=PRICING_MAX_AGE_DAYS):
        _warn_about_pricing_catalog(
            f"The pricing catalog is more than {PRICING_MAX_AGE_DAYS} days old. "
            "Cost estimates can use old rates."
        )


def _warn_about_pricing_catalog(message: str) -> None:
    warnings.warn(message, PricingCatalogWarning, stacklevel=3)


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
    _warn_if_catalog_is_not_current(catalog)
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
        last_updated_utc=str(catalog.get("last_updated_utc", "")),
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
    "PRICING_MAX_AGE_DAYS",
    "PricingCatalogWarning",
    "resolve_model_pricing",
]
