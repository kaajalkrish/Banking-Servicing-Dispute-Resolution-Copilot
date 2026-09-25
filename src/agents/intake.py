"""Intake worker: clarify ambiguous requests (AC-04).

Used when the supervisor marks a request ambiguous. Asks one focused clarifying
question rather than guessing. No tools needed.
"""

from __future__ import annotations

from typing import Any

from src.agents._common import compose_answer, latest_user_text, record_result

SYSTEM = (
    "You are a retail-bank servicing assistant. The customer's request is ambiguous. "
    "Ask ONE short, specific clarifying question so it can be routed correctly. Offer "
    "the main things you can help with: balances/transactions, disputes, product/fee "
    "questions, and simple service requests."
)


async def intake_node(state: dict[str, Any], *, tools: list[Any], llm: Any) -> dict[str, Any]:
    text = latest_user_text(state)
    answer = await compose_answer(llm, SYSTEM, f"Customer said: {text}\n\nAsk one clarifying question.")
    return record_result(state, "intake", answer)
