"""Dispute worker: capture a disputed transaction, check eligibility, draft
next step (AC-02).

Raw customer text is quarantined and passed through a schema-constrained,
tool-less extraction step (never raw regex-on-free-text for the fields that
matter) to get a transaction id and a reason hint (NFR-03, AC-06); eligibility
against servicing policy is a DETERMINISTIC check (check_dispute_eligibility,
driven by the dispute-windows resource) -- the RAG citation only enriches the
explanation, it never overrides the deterministic decision. A dispute is
always captured as a DRAFT for a human agent, whether or not it is within the
standard window (servicing policy allows discretionary review outside it);
the copilot never resolves or commits an outcome (D-13).
"""

from __future__ import annotations

import json
from typing import Any

from src.agents._common import compose_answer, get_tool, latest_user_text, memory_context_block, record_result
from src.context.isolate import isolate_for_worker
from src.context.quarantine import extract_dispute_fields
from src.tools.resilience import resilient_ainvoke

SYSTEM = (
    "You are a retail-bank dispute intake assistant. You may DRAFT a dispute for a "
    "human agent to review; you must never state that a refund or resolution is "
    "approved. Explain the eligibility finding briefly and factually, cite the "
    "policy passage if one is given, and be clear a human agent will review the case."
)


async def dispute_node(state: dict[str, Any], *, tools: list[Any], llm: Any) -> dict[str, Any]:
    iso = isolate_for_worker(state, "dispute")
    text = latest_user_text(iso)
    fields = await extract_dispute_fields(llm, text)

    if not fields.transaction_id:
        msg = (
            "I can help raise a dispute. Which transaction is it? Please share the "
            "transaction id (e.g. TXN0001234) or the date, amount and merchant."
        )
        return record_result(state, "dispute", msg, requires_human_review=True)

    reason = fields.reason_hint if fields.reason_hint != "unclear" else "unrecognized_charge"
    customer_id = iso["customer_id"]

    eligibility_tool = get_tool(tools, "check_dispute_eligibility")
    eligibility = await resilient_ainvoke(
        eligibility_tool,
        {"customer_id": customer_id, "transaction_id": fields.transaction_id, "reason": reason},
        tool_name="check_dispute_eligibility",
    )

    # RAG citation enriches the explanation; it never decides eligibility.
    citation: dict[str, str] | None = None
    rag_tool = get_tool(tools, "policy_search")
    if rag_tool is not None:
        rag_result = await resilient_ainvoke(
            rag_tool, {"query": f"dispute eligibility window for {reason}"}, tool_name="policy_search"
        )
        if isinstance(rag_result, dict) and rag_result.get("citations"):
            citation = rag_result["citations"][0]

    dispute_tool = get_tool(tools, "create_dispute_case")
    dispute_result = await resilient_ainvoke(
        dispute_tool,
        {
            "customer_id": customer_id,
            "transaction_id": fields.transaction_id,
            "reason": reason,
            "description": text[:500],
        },
        tool_name="create_dispute_case",
    )

    answer = await compose_answer(
        llm,
        SYSTEM,
        f"Customer said: {text}\n{memory_context_block(iso)}\n"
        f"Eligibility check: {json.dumps(eligibility, default=str)}\n"
        f"Supporting citation: {citation}\n"
        f"Draft dispute result: {json.dumps(dispute_result, default=str)}\n\n"
        "Confirm the dispute has been DRAFTED for human review, state the eligibility "
        "finding, and the next step. Do not promise a refund.",
    )
    citations = [citation] if citation else []
    return record_result(state, "dispute", answer, requires_human_review=True, citations=citations)
