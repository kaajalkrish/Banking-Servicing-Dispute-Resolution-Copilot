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
    "- account_servicing: balance, recent transactions, statement summary\n"
    "- dispute: a disputed / unauthorized / duplicate transaction\n"
    "- product_info: product, fee or servicing-policy questions\n"
    "- intake: the request is ambiguous and needs one clarifying question\n"
    "- escalate_human: out of scope, or needs a human (e.g. money movement, legal)\n"
    "Set needs_clarification=true only when the request is genuinely ambiguous."
)


async def supervisor_node(state: dict[str, Any], *, llm: Any) -> dict[str, Any]:
    """Increment the step counter and decide the next route."""
    step = int(state.get("step_count", 0)) + 1

    # If a worker has already answered, we are done -> finalize.
    if state.get("worker_results"):
        return {"route": "finalize", "step_count": step}

    text = latest_user_text(state)
    structured = llm.with_structured_output(RouteDecision)
    decision: RouteDecision = await structured.ainvoke(
        [SystemMessage(content=SYSTEM), HumanMessage(content=text)]
    )
    route = "intake" if decision.needs_clarification else decision.worker
    if route not in _VALID_ROUTES:
        route = "escalate_human"
    return {"route": route, "intent": decision.reason, "step_count": step}


def route_from_supervisor(state: dict[str, Any]) -> str:
    """Pure conditional-edge function: map state -> next node name."""
    route = state.get("route", "")
    return route if route in _VALID_ROUTES else "escalate_human"
