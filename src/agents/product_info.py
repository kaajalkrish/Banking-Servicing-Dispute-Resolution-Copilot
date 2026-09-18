"""Product-info worker: product, fee and servicing-policy questions (AC-03).

Phase 1 answers from a small static fee reference and abstains when a question
is outside it. Phase 2 replaces this with the agentic-RAG tool over the policy
corpus (grounded, cited answers with proper abstention).
"""

from __future__ import annotations

from typing import Any

from src.agents._common import compose_answer, latest_user_text, record_result

# Minimal synthetic fee reference (superseded by the RAG policy corpus in P2).
FEE_REFERENCE = {
    "monthly_maintenance_fee_usd": 5.0,
    "overdraft_fee_usd": 30.0,
    "atm_out_of_network_fee_usd": 3.0,
    "foreign_transaction_fee_pct": 3.0,
    "card_replacement_fee_usd": 0.0,
}

SYSTEM = (
    "You are a retail-bank product-and-fee assistant. Answer ONLY from the provided "
    "fee reference. If the question is not covered by it, say you don't have that "
    "information yet and offer to connect the customer to the right resource — do "
    "not guess."
)


async def product_info_node(state: dict[str, Any], *, tools: list[Any], llm: Any) -> dict[str, Any]:
    text = latest_user_text(state)
    answer = await compose_answer(
        llm,
        SYSTEM,
        f"Customer asked: {text}\n\nFee reference (USD unless noted):\n{FEE_REFERENCE}\n\n"
        "Answer concisely, or abstain if not covered.",
    )
    return record_result(state, "product_info", answer)
