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

import asyncio
import json
from typing import Any

from src.agents._common import compose_answer, get_tool, latest_user_text, memory_context_block, record_result
from src.config import settings
from src.context.isolate import isolate_for_worker
from src.context.quarantine import extract_dispute_fields

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
    customer_id = iso["customer_id"]

    # Status check on an existing dispute is a read, not a new filing -- it
    # doesn't need eligibility re-checked or a second case drafted (found
    # live: without this branch, "what's the status of dispute DSP00001"
    # created a brand-new duplicate draft instead of just answering).
    if fields.dispute_id and not fields.transaction_id:
        status_tool = get_tool(tools, "get_dispute_status", authenticated_customer_id=customer_id)
        status_result = await status_tool.ainvoke({"customer_id": customer_id, "dispute_id": fields.dispute_id})
        answer = await compose_answer(
            llm,
            SYSTEM,
            f"Customer asked about dispute {fields.dispute_id}: {text}\n"
            f"Status lookup result: {json.dumps(status_result, default=str)}\n\n"
            "Report the dispute's current status factually. Do not promise a refund "
            "or state an outcome that isn't in the status result.",
        )
        return record_result(state, "dispute", answer, citations=[])

    if not fields.transaction_id:
        msg = (
            "I can help raise a dispute. Which transaction is it? Please share the "
            "transaction id (e.g. TXN0001234) or the date, amount and merchant."
        )
        return record_result(state, "dispute", msg, requires_human_review=True)

    reason = fields.reason_hint if fields.reason_hint != "unclear" else "unrecognized_charge"

    # tools are already resilient + logged (P3-07 registry) — just invoke.
    eligibility_tool = get_tool(tools, "check_dispute_eligibility", authenticated_customer_id=customer_id)
    rag_tool = get_tool(tools, "policy_search", authenticated_customer_id=customer_id)
    dispute_tool = get_tool(tools, "create_dispute_case", authenticated_customer_id=customer_id)

    eligibility_args = {"customer_id": customer_id, "transaction_id": fields.transaction_id, "reason": reason}
    rag_args = {"query": f"dispute eligibility window for {reason}"}
    dispute_args = {
        "customer_id": customer_id,
        "transaction_id": fields.transaction_id,
        "reason": reason,
        "description": text[:500],
    }

    if settings.optimization_profile == "baseline":
        # Sequential: the pre-optimization code path, kept only so the §8.1
        # before/after comparison has real code to compare against (never
        # used by default — see docs/optimization-note.md).
        eligibility = await eligibility_tool.ainvoke(eligibility_args)
        rag_result = await rag_tool.ainvoke(rag_args) if rag_tool is not None else None
        dispute_result = await dispute_tool.ainvoke(dispute_args)
    else:
        # None of these three calls' arguments depend on another call's
        # result (dispute_args doesn't need eligibility or the citation), so
        # they can run concurrently (P5-13). Eligibility and dispute creation
        # are fast local MCP calls; the RAG policy search runs its own
        # retrieve/grade/answer subgraph and is consistently the slowest of
        # the three — serializing everything behind it was wasted wall-clock
        # time for no reason.
        calls = [eligibility_tool.ainvoke(eligibility_args), dispute_tool.ainvoke(dispute_args)]
        if rag_tool is not None:
            calls.append(rag_tool.ainvoke(rag_args))
        results = await asyncio.gather(*calls)
        eligibility, dispute_result = results[0], results[1]
        rag_result = results[2] if rag_tool is not None else None

    # RAG citation enriches the explanation; it never decides eligibility.
    citation: dict[str, str] | None = None
    if isinstance(rag_result, dict) and rag_result.get("citations"):
        citation = rag_result["citations"][0]

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
