"""Published Gemini per-token prices, used by golden_signals.py's cost
estimate (§7.3, §8).

Prices are copied from Google's published Gemini Developer API pricing page
(SOURCE_URL, read on CONFIRMED_ON), "Standard" paid-tier rate, text input.
They are NOT recalled from memory -- this assistant's training predates the
models used in this project, so plan.md's M-3 [MANUAL] step required them to
be confirmed against the published page before any cost figure was emitted.

Basis of the estimate: every run in this project used the Gemini free tier
(actual billed cost: $0). The figure golden_signals.py reports is therefore
what the same token volume WOULD cost at the paid Standard list price
("cost = tokens x published price", ref-doc.md §8), not money actually
spent. Thinking tokens are billed as output tokens by Google, and the
`llm.token_count.completion` attribute is assumed to include them; if a
model reports them separately the estimate would under-count output cost.

get_price() still raises for a model with no entry, so a newly used model
makes golden_signals.py's cost field visibly absent rather than silently $0.
"""

from __future__ import annotations

from typing import TypedDict


class ModelPrice(TypedDict):
    input_per_1m: float
    output_per_1m: float


PRICES_USD_PER_1M_TOKENS: dict[str, ModelPrice] = {
    "gemini-3.5-flash": {"input_per_1m": 1.50, "output_per_1m": 9.00},
    "gemini-3.5-flash-lite": {"input_per_1m": 0.30, "output_per_1m": 2.50},
    "gemini-3.1-flash-lite": {"input_per_1m": 0.25, "output_per_1m": 1.50},
}

# Where and when the prices above were confirmed.
SOURCE_URL: str | None = "https://ai.google.dev/gemini-api/docs/pricing"
CONFIRMED_ON: str | None = "2026-09-19"  # ISO date

PRICE_BASIS = (
    "paid-tier Standard list price, text input; runs used the free tier, "
    "so this is the equivalent cost at list price, not billed spend"
)


class PriceNotConfirmedError(RuntimeError):
    pass


def get_price(model_name: str) -> ModelPrice:
    if model_name not in PRICES_USD_PER_1M_TOKENS:
        raise PriceNotConfirmedError(
            f"no confirmed price for model {model_name!r} -- see src/observability/pricing.py "
            "(plan.md [MANUAL] M-3); add it to PRICES_USD_PER_1M_TOKENS from the published "
            "pricing page and update SOURCE_URL/CONFIRMED_ON before running "
            "golden_signals.py for real evidence"
        )
    return PRICES_USD_PER_1M_TOKENS[model_name]


def estimate_cost_usd(model_name: str, *, input_tokens: int, output_tokens: int) -> float:
    price = get_price(model_name)
    return (input_tokens / 1_000_000) * price["input_per_1m"] + (
        output_tokens / 1_000_000
    ) * price["output_per_1m"]
