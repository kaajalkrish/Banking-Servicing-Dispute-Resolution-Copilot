"""Supervisor: routes each request to a worker via a structured RouteDecision.

The supervisor emits a validated RouteDecision (structured output). Once a worker
has produced a result it routes to `finalize`. route_from_supervisor is a PURE
function used as the conditional-edge function, so routing is unit-testable
without any network (§7.6). Out-of-scope requests route to escalate_human;
ambiguous ones route to intake for clarification (AC-04).
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._common import latest_user_text
from src.llm import ainvoke_with_backoff
from src.schemas import RouteDecision

_VALID_ROUTES = {
    "intake",
    "account_servicing",
    "dispute",
    "product_info",
    "escalate_human",
    "finalize",
}

SYSTEM = (
    "You are the supervisor of a retail-bank servicing copilot. Choose the single "
    "best worker for the customer's request:\n"
    "- account_servicing: balance, recent transactions, statement summary, or a "
    "simple service request (lost/stolen card replacement, a statement copy, a "
    "credit-limit change) -- including checking facts about the customer's own "
    "transactions (e.g. 'did I get charged twice', 'is there a transaction I "
    "don't recognize') when they are only asking what happened, not yet asking "
    "to file or report a dispute\n"
    "- dispute: the customer wants to FILE or REPORT a specific transaction as "
    "unauthorized/duplicate/wrong right now, or is asking about the STATUS of a "
    "dispute they already filed. Do NOT route here for a general question about "
    "dispute policy/eligibility/procedure that isn't tied to filing one now -- "
    "route those to product_info instead (e.g. 'how long do I have to dispute a "
    "charge', 'what should I do if I see an unauthorized transaction', 'can I "
    "still dispute something from 200 days ago' are all policy questions, not "
    "filing intent)\n"
    "- product_info: product, fee or servicing-policy questions, including "
    "general questions about dispute rules/eligibility/process that are not "
    "tied to a specific transaction the customer wants to dispute right now\n"
    "- intake: the request is ambiguous and needs one clarifying question\n"
    "- escalate_human: out of scope, or needs a human (e.g. money movement, legal)\n"
    "Set needs_clarification=true only when the request is genuinely ambiguous."
)


async def supervisor_node(state: dict[str, Any], *, llm: Any) -> dict[str, Any]:
    """Increment the step counter and decide the next route."""
    step = int(state.get("step_count", 0)) + 1
    max_steps = int(state.get("max_steps", 0)) or 12

    # Loop/cascade guard: too many hops -> finalize with escalation (§7.6, NFR-04).
    if step > max_steps:
        return {
            "route": "finalize",
            "escalated": True,
            "requires_human_review": True,
            "step_count": step,
        }

    # If a worker has already answered, we are done -> finalize.
    if state.get("worker_results"):
        return {"route": "finalize", "step_count": step}

    text = latest_user_text(state)
    structured = llm.with_structured_output(RouteDecision)
    # Retries transient errors (timeouts/429/5xx) so a momentary Gemini hiccup
    # degrades gracefully instead of crashing the run (NFR-04).
    decision: RouteDecision = await ainvoke_with_backoff(
        structured, [SystemMessage(content=SYSTEM), HumanMessage(content=text)]
    )
    route = "intake" if decision.needs_clarification else decision.worker
    if route not in _VALID_ROUTES:
        route = "escalate_human"
    return {"route": route, "intent": decision.reason, "step_count": step}


def route_from_supervisor(state: dict[str, Any]) -> str:
    """Pure conditional-edge function: map state -> next node name."""
    route = state.get("route", "")
    return route if route in _VALID_ROUTES else "escalate_human"
