"""Cost-estimate arithmetic and the fail-loud behaviour for unpriced models
(§7.3, §8: cost = tokens x published price)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.observability import pricing
from src.observability.golden_signals import _cost_usd
from src.observability.pricing import PriceNotConfirmedError, estimate_cost_usd, get_price


def test_estimate_cost_is_tokens_times_published_price():
    price = get_price("gemini-3.1-flash-lite")
    cost = estimate_cost_usd("gemini-3.1-flash-lite", input_tokens=2_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(2 * price["input_per_1m"] + price["output_per_1m"])


def test_unpriced_model_raises_instead_of_costing_zero():
    with pytest.raises(PriceNotConfirmedError):
        get_price("gemini-does-not-exist")


def test_prices_carry_source_and_date():
    assert pricing.SOURCE_URL and pricing.SOURCE_URL.startswith("https://")
    assert pricing.CONFIRMED_ON and len(pricing.CONFIRMED_ON) == 10


def _spans(models: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "span_kind": ["LLM"] * len(models),
            "attributes.llm.model_name": models,
            "attributes.llm.token_count.prompt": [1_000_000] * len(models),
            "attributes.llm.token_count.completion": [1_000_000] * len(models),
        }
    )


def test_cost_report_records_source_basis_and_per_model_split():
    out = _cost_usd(_spans(["gemini-3.5-flash", "gemini-3.1-flash-lite"]), {})
    assert out["total_usd"] == pytest.approx((1.50 + 9.00) + (0.25 + 1.50))
    assert set(out["per_model_usd"]) == {"gemini-3.5-flash", "gemini-3.1-flash-lite"}
    assert out["price_source_url"] == pricing.SOURCE_URL
    assert out["prices_confirmed_on"] == pricing.CONFIRMED_ON
    assert "free tier" in out["basis"]


def test_cost_report_is_null_with_note_when_a_model_is_unpriced():
    out = _cost_usd(_spans(["gemini-3.5-flash", "gemini-unpriced"]), {})
    assert out["total_usd"] is None
    assert "gemini-unpriced" in out["note"]
