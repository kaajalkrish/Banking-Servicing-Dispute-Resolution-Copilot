"""Dispute worker: capture a disputed transaction, draft next step (AC-02).

Creates a DRAFT dispute only — the copilot never commits a resolution or money
movement; every dispute outcome is flagged for human review (D-13). Eligibility
against servicing policy is added in Phase 2 (RAG + dispute-windows resource).
"""

from __future__ import annotations

import json
from typing import Any

from src.agents._common import (
    compose_answer,
    find_transaction_id,
    get_tool,
    latest_user_text,
    record_result,
)
from src.tools.resilience import resilient_ainvoke

SYSTEM = (
    "You are a retail-bank dispute intake assistant. You may DRAFT a dispute for a "
    "human agent to review; you must never state that a refund or resolution is "
    "approved. Be clear that a human agent will review the case."
)


async def dispute_node(state: dict[str, Any], *, tools: list[Any], llm: Any) -> dict[str, Any]:
    text = latest_user_text(state)
    txn_id = find_transaction_id(text)

    if not txn_id:
        # No transaction identified: ask for the specific transaction (clarify).
        msg = (
            "I can help raise a dispute. Which transaction is it? Please share the "
            "transaction id (e.g. TXN0001234) or the date, amount and merchant."
        )
        return record_result(state, "dispute", msg, requires_human_review=True)

    tool = get_tool(tools, "create_dispute_case")
    args = {
        "customer_id": state["customer_id"],
        "transaction_id": txn_id,
        "reason": "unrecognized_charge",
        "description": text[:500],
    }
    result = await resilient_ainvoke(tool, args, tool_name="create_dispute_case") if tool else {
        "error": {"type": "Unavailable", "message": "dispute tool unavailable"}
    }
    answer = await compose_answer(
        llm,
        SYSTEM,
        f"Customer said: {text}\n\nDraft dispute result:\n{json.dumps(result, default=str)}\n\n"
        "Confirm the dispute has been DRAFTED for human review and state the next step. "
        "Do not promise a refund.",
    )
    return record_result(state, "dispute", answer, requires_human_review=True)
