from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import warnings

import pytest

from compendiumscribe.research import pricing as pricing_module
from compendiumscribe.research.pricing import (
    CATALOG_PATH,
    PricingCatalogWarning,
    resolve_model_pricing,
)


NOW_UTC = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_pricing_catalog_state(monkeypatch: pytest.MonkeyPatch) -> None:
    pricing_module._load_catalog.cache_clear()
    monkeypatch.setattr(pricing_module, "_catalog_freshness_checked", False)
    monkeypatch.setattr(pricing_module, "_utc_now", lambda: NOW_UTC)


def test_standard_catalog_contains_only_gpt_5_6_models() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    assert set(catalog["models"]) == {
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
    }
    assert catalog["last_updated_utc"] == "2026-08-29T00:00:00Z"


@pytest.mark.parametrize(
    (
        "model",
        "input_rate",
        "cached_input_rate",
        "output_rate",
        "long_input_rate",
        "long_cached_input_rate",
        "long_output_rate",
    ),
    [
        ("gpt-5.6-sol", 4.0, 0.4, 20.0, 8.0, 0.8, 30.0),
        ("gpt-5.6-terra", 2.0, 0.2, 12.0, 4.0, 0.4, 18.0),
        ("gpt-5.6-luna", 0.2, 0.02, 1.2, 0.4, 0.04, 1.8),
    ],
)
def test_resolve_standard_model_pricing(
    model: str,
    input_rate: float,
    cached_input_rate: float,
    output_rate: float,
    long_input_rate: float,
    long_cached_input_rate: float,
    long_output_rate: float,
) -> None:
    pricing = resolve_model_pricing(model)

    assert pricing is not None
    assert pricing.resolved_model == model
    assert pricing.input_per_1m_usd == input_rate
    assert pricing.cached_input_per_1m_usd == cached_input_rate
    assert pricing.output_per_1m_usd == output_rate
    assert pricing.long_context_threshold_tokens == 272_000
    assert pricing.long_context_input_per_1m_usd == long_input_rate
    assert pricing.long_context_cached_input_per_1m_usd == long_cached_input_rate
    assert pricing.long_context_output_per_1m_usd == long_output_rate
    assert pricing.tool_call_prices_per_1k_usd["web_search_call"] == 10.0
    assert pricing.tool_call_prices_per_1k_usd["file_search_call"] == 2.5


def test_unknown_model_returns_none() -> None:
    pricing = resolve_model_pricing("unknown-research-model")

    assert pricing is None


@pytest.mark.parametrize(
    "last_updated_utc",
    [
        "2026-08-29T12:00:00Z",
        "2026-05-31T12:00:00Z",
    ],
    ids=["fresh", "exactly-90-days-old"],
)
def test_current_pricing_timestamp_does_not_warn(
    tmp_path: Path,
    last_updated_utc: str,
) -> None:
    catalog_path = _write_catalog(tmp_path, last_updated_utc=last_updated_utc)

    with warnings.catch_warnings(record=True) as warnings_seen:
        warnings.simplefilter("always")
        pricing = resolve_model_pricing("gpt-5.6-sol", catalog_path=catalog_path)

    assert pricing is not None
    assert list(warnings_seen) == []


def test_stale_pricing_timestamp_warns_once_per_process(tmp_path: Path) -> None:
    catalog_path = _write_catalog(
        tmp_path,
        last_updated_utc="2026-05-31T11:59:59Z",
    )

    with pytest.warns(PricingCatalogWarning, match="more than 90 days old"):
        first = resolve_model_pricing("gpt-5.6-sol", catalog_path=catalog_path)
    with warnings.catch_warnings(record=True) as warnings_seen:
        warnings.simplefilter("always")
        second = resolve_model_pricing("gpt-5.6-sol", catalog_path=catalog_path)

    assert first is not None
    assert second is not None
    assert list(warnings_seen) == []


@pytest.mark.parametrize(
    ("last_updated_utc", "expected_message"),
    [
        (None, "has no last_updated_utc timestamp"),
        ("not-a-timestamp", "has an invalid last_updated_utc timestamp"),
        ("2026-08-29T12:00:00", "must use UTC"),
    ],
    ids=["missing", "malformed", "not-timezone-aware"],
)
def test_invalid_pricing_timestamp_warns_and_continues(
    tmp_path: Path,
    last_updated_utc: str | None,
    expected_message: str,
) -> None:
    catalog_path = _write_catalog(tmp_path, last_updated_utc=last_updated_utc)

    with pytest.warns(PricingCatalogWarning, match=expected_message):
        pricing = resolve_model_pricing("gpt-5.6-sol", catalog_path=catalog_path)

    assert pricing is not None


def _write_catalog(
    tmp_path: Path,
    *,
    last_updated_utc: str | None,
) -> Path:
    catalog = {
        "source_url": "https://developers.openai.com/api/docs/pricing",
        "tier": "standard",
        "tool_call_prices_per_1k_usd": {},
        "models": {
            "gpt-5.6-sol": {
                "input_per_1m_usd": 4.0,
                "cached_input_per_1m_usd": 0.4,
                "output_per_1m_usd": 20.0,
            }
        },
    }
    if last_updated_utc is not None:
        catalog["last_updated_utc"] = last_updated_utc
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path
