"""LangGraph graph wiring (ref-doc.md §7.1).

supervisor + four workers (intake, account_servicing, dispute, product_info)
plus escalate_human and finalize, connected with conditional edges through the
pure route_from_supervisor function. Structured output is produced at node
boundaries (RouteDecision, FinalAnswer). The checkpointer and the step/recursion
guard are added in P1-15.

build_graph injects the models and tools so tests can pass fakes (no network).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import partial
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from src.agents.account_servicing import account_servicing_node
from src.agents.dispute import dispute_node
from src.agents.escalate import escalate_node
from src.agents.intake import intake_node
from src.agents.product_info import product_info_node
from src.agents.supervisor import route_from_supervisor, supervisor_node
from src.config import settings
from src.schemas import FinalAnswer
from src.state import CopilotState

_WORKER_NODES = {
    "intake": intake_node,
    "account_servicing": account_servicing_node,
    "dispute": dispute_node,
    "product_info": product_info_node,
}


async def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Package the final answer and append it as the assistant message."""
    results = state.get("worker_results", [])
    escalated = bool(state.get("escalated"))
    requires_human = bool(state.get("requires_human_review"))

    if results:
        content = results[-1]["content"]
        citations = results[-1].get("citations", [])
    elif escalated:
        content = "This request needs a human banking agent, who will follow up."
        citations = []
    else:
        content = "I couldn't complete that request. Let me connect you to a human agent."
        citations = []

    risk_tier = "high" if (escalated or requires_human) else "low"
    final = FinalAnswer(
        answer=content,
        citations=citations,
        requires_human_review=requires_human,
        risk_tier=risk_tier,
        escalated=escalated,
    )
    return {"final_answer": final.model_dump(), "messages": [AIMessage(content=content)]}


def build_graph(*, supervisor_llm: Any, worker_llm: Any, tools: list[Any], checkpointer: Any = None):
    """Build and compile the copilot graph with injected models and tools."""
    g = StateGraph(CopilotState)

    g.add_node("supervisor", partial(supervisor_node, llm=supervisor_llm))
    for name, fn in _WORKER_NODES.items():
        g.add_node(name, partial(fn, tools=tools, llm=worker_llm))
    g.add_node("escalate_human", escalate_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "intake": "intake",
            "account_servicing": "account_servicing",
            "dispute": "dispute",
            "product_info": "product_info",
            "escalate_human": "escalate_human",
            "finalize": "finalize",
        },
    )
    # Workers return to the supervisor, which then routes to finalize.
    for name in _WORKER_NODES:
        g.add_edge(name, "supervisor")
    g.add_edge("escalate_human", "finalize")
    g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer)


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[Any]:
    """Async context manager yielding an AsyncSqliteSaver at the configured path.

    The sqlite file lives under STATE_DIR (gitignored) so short-term thread state
    persists across turns without ever being committed.
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    settings.ensure_dirs()
    conn = str(settings.state_dir / "checkpoints.sqlite")
    async with AsyncSqliteSaver.from_conn_string(conn) as saver:
        yield saver


def run_config(thread_id: str) -> dict[str, Any]:
    """Invoke config: the checkpointer thread id and the recursion limit (NFR-04)."""
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.recursion_limit,
    }
