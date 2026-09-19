"""Account-servicing worker: balance, transactions, statement summary (AC-01).

Least privilege: bound only to the read-only account tools. The customer_id is
taken from state (authenticated), never from model output (AC-06).
"""

from __future__ import annotations

import json
from typing import Any

from src.agents._common import compose_answer, get_tool, latest_user_text, memory_context_block, record_result
from src.context.isolate import isolate_for_worker

SYSTEM = (
    "You are a retail-bank account servicing assistant. Answer only from the tool "
    "result provided. Never invent balances, transactions or request statuses. "
    "Amounts and account references in the tool result are already masked; keep "
    "them masked."
)

# Each request type matches on (anchor word present) AND (any trigger word present),
# so phrasing like "I lost my card, I need a replacement" matches without needing an
# exact phrase.
_SERVICE_REQUEST_TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "card_replacement": ("card", ("lost", "stolen", "damaged", "replace", "replacement", "new")),
    "statement_copy": ("statement", ("copy", "mail", "paper", "send")),
    "limit_change": ("limit", ("increase", "raise", "change", "higher", "credit")),
}


def _match_service_request(text: str) -> str | None:
    t = (text or "").lower()
    for request_type, (anchor, triggers) in _SERVICE_REQUEST_TYPES.items():
        if anchor in t and any(trigger in t for trigger in triggers):
            return request_type
    return None


def _choose(text: str) -> str:
    t = (text or "").lower()
    if _match_service_request(t):
        return "submit_service_request"
    if any(w in t for w in ("transaction", "recent", "history", "spent", "charge")):
        return "list_recent_transactions"
    if any(w in t for w in ("statement", "summary", "summarize", "breakdown", "category")):
        return "get_statement_summary"
    return "get_account_balance"


def _service_request_type(text: str) -> str:
    return _match_service_request(text) or "card_replacement"  # only reached via _choose's same check


async def account_servicing_node(
    state: dict[str, Any], *, tools: list[Any], llm: Any
) -> dict[str, Any]:
    # Isolated context window: this worker only reads the state slice it needs
    # (customer_id, messages, account_ref) — never another worker's draft or
    # dispute state (src/context/isolate.py).
    iso = isolate_for_worker(state, "account_servicing")
    text = latest_user_text(iso)
    tool_name = _choose(text)
    tool = get_tool(tools, tool_name, authenticated_customer_id=iso["customer_id"])

    if tool is None:
        return record_result(state, "account_servicing", "That capability is unavailable right now.")

    if tool_name == "submit_service_request":
        args: dict[str, Any] = {
            "customer_id": iso["customer_id"],
            "request_type": _service_request_type(text),
            "details": text[:500],
        }
    else:
        args = {"customer_id": iso["customer_id"]}
        if iso.get("account_ref"):
            args["account_ref"] = iso["account_ref"]

    # tools are already resilient + logged (P3-07 registry) — just invoke.
    result = await tool.ainvoke(args)
    answer = await compose_answer(
        llm,
        SYSTEM,
        f"Customer asked: {text}\n{memory_context_block(iso)}\n"
        f"Tool `{tool_name}` returned:\n{json.dumps(result, default=str)}\n\n"
        "Write a concise, accurate answer for the customer.",
    )
    return record_result(state, "account_servicing", answer)
