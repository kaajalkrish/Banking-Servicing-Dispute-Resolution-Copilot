"""Published Gemini per-token prices, used by golden_signals.py's cost
estimate (§7.3, §8).

Prices are NOT hardcoded from memory -- this assistant's training predates
the models actually used in this project (gemini-3.5-flash-lite,
gemini-3.1-flash-lite; see STATUS.md's "Side discovery"), so any number
guessed here would be a fabricated financial figure, which the
Evidence-in-Repo Rule and this project's own honesty rules (plan.md #6, #8)
both forbid. plan.md's own M-3 [MANUAL] step says exactly this: a human
must confirm current published prices before the cost estimate is real.

PRICES_USD_PER_1M_TOKENS is intentionally empty until that confirmation
happens; source_url/confirmed_on stay unset (None) until it's filled in.
get_price() raises rather than silently costing a run at $0 -- a missing
price should make golden_signals.py's cost field visibly absent, not wrong.
"""

from __future__ import annotations

from typing import TypedDict


class ModelPrice(TypedDict):
    input_per_1m: float
    output_per_1m: float


# Fill in after M-3: {model_name: {"input_per_1m": ..., "output_per_1m": ...}}
PRICES_USD_PER_1M_TOKENS: dict[str, ModelPrice] = {}

# Where and when the prices above were confirmed (required once populated).
SOURCE_URL: str | None = None
CONFIRMED_ON: str | None = None  # ISO date, e.g. "2026-09-20"


class PriceNotConfirmedError(RuntimeError):
    pass


def get_price(model_name: str) -> ModelPrice:
    if model_name not in PRICES_USD_PER_1M_TOKENS:
        raise PriceNotConfirmedError(
            f"no confirmed price for model {model_name!r} -- see src/observability/pricing.py "
            "(plan.md [MANUAL] M-3); populate PRICES_USD_PER_1M_TOKENS, SOURCE_URL and "
            "CONFIRMED_ON before running golden_signals.py for real evidence"
        )
    return PRICES_USD_PER_1M_TOKENS[model_name]


def estimate_cost_usd(model_name: str, *, input_tokens: int, output_tokens: int) -> float:
    price = get_price(model_name)
    return (input_tokens / 1_000_000) * price["input_per_1m"] + (
        output_tokens / 1_000_000
    ) * price["output_per_1m"]
