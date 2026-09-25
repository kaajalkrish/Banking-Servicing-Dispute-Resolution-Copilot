"""Escalation node: hand off out-of-scope or high-risk requests to a human (AC-04).

Deterministic (no LLM/tools needed): records a handoff message and sets the
escalation flag so finalize returns a safe hand-to-human answer.
"""

from __future__ import annotations

from typing import Any

from src.agents._common import latest_user_text, record_result

HANDOFF = (
    "This request needs a human banking agent. I've noted your request and a human "
    "agent will follow up. Is there anything else I can help you with in the meantime?"
)


async def escalate_node(state: dict[str, Any], **_: Any) -> dict[str, Any]:
    _ = latest_user_text(state)
    update = record_result(state, "escalate_human", HANDOFF, requires_human_review=True)
    update["escalated"] = True
    return update
