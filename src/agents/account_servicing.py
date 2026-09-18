"""Account-servicing worker: balance, transactions, statement summary (AC-01).

Least privilege: bound only to the read-only account tools. The customer_id is
taken from state (authenticated), never from model output (AC-06).
"""

from __future__ import annotations

import json
from typing import Any

from src.agents._common import compose_answer, get_tool, latest_user_text, record_result
from src.tools.resilience import resilient_ainvoke

SYSTEM = (
    "You are a retail-bank account servicing assistant. Answer only from the tool "
    "result provided. Never invent balances or transactions. Amounts and account "
    "references in the tool result are already masked; keep them masked."
)


def _choose(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ("transaction", "recent", "history", "spent", "charge")):
        return "list_recent_transactions"
    if any(w in t for w in ("statement", "summary", "summarize", "breakdown", "category")):
        return "get_statement_summary"
    return "get_account_balance"


async def account_servicing_node(
    state: dict[str, Any], *, tools: list[Any], llm: Any
) -> dict[str, Any]:
    text = latest_user_text(state)
    tool_name = _choose(text)
    tool = get_tool(tools, tool_name)
    args: dict[str, Any] = {"customer_id": state["customer_id"]}
    if state.get("account_ref"):
        args["account_ref"] = state["account_ref"]

    if tool is None:
        return record_result(state, "account_servicing", "That capability is unavailable right now.")

    result = await resilient_ainvoke(tool, args, tool_name=tool_name)
    answer = await compose_answer(
        llm,
        SYSTEM,
        f"Customer asked: {text}\n\nTool `{tool_name}` returned:\n{json.dumps(result, default=str)}\n\n"
        "Write a concise, accurate answer for the customer.",
    )
    return record_result(state, "account_servicing", answer)
