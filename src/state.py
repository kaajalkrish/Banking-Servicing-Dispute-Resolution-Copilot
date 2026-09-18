"""Typed LangGraph state (ref-doc.md §3.3 bullet 1, §7.1).

The messages channel uses the add_messages reducer. The authenticated
``customer_id`` is injected by the CLI/API and must NEVER be overwritten from
LLM output (AC-06) — worker/tool code reads it from state only. Step counting
supports the loop/cascade guard (§7.6). Fields for later phases (memory,
context, guardrail decisions) are declared optional here so the schema is
stable across the build.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

WorkerName = Literal[
    "intake",
    "account_servicing",
    "dispute",
    "product_info",
    "escalate_human",
    "finalize",
]


class CopilotState(TypedDict, total=False):
    # Conversation
    messages: Annotated[list, add_messages]

    # Identity (authenticated; injected — not from the model)
    customer_id: str
    account_ref: str | None

    # Routing / control
    intent: str
    route: str
    step_count: int
    max_steps: int

    # Outcome
    requires_human_review: bool
    escalated: bool
    final_answer: dict[str, Any]
    worker_results: list[dict[str, Any]]

    # Placeholders wired by later phases (context engineering, memory, guardrails)
    context: dict[str, Any]
    memory: dict[str, Any]
    guardrail: dict[str, Any]


def new_state(customer_id: str, user_text: str, *, max_steps: int, account_ref: str | None = None) -> CopilotState:
    """Build an initial state for one conversation turn."""
    from langchain_core.messages import HumanMessage

    return CopilotState(
        messages=[HumanMessage(content=user_text)],
        customer_id=customer_id,
        account_ref=account_ref,
        intent="",
        route="",
        step_count=0,
        max_steps=max_steps,
        requires_human_review=False,
        escalated=False,
        final_answer={},
        worker_results=[],
    )
