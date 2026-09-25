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

from src.agents._common import latest_user_text
from src.agents.account_servicing import account_servicing_node
from src.agents.dispute import dispute_node
from src.agents.escalate import escalate_node
from src.agents.intake import intake_node
from src.agents.product_info import product_info_node
from src.agents.supervisor import route_from_supervisor, supervisor_node
from src.config import settings
from src.context.select import select_context
from src.context.summarization import maybe_summarize
from src.schemas import FinalAnswer
from src.state import CopilotState
from src.tools.registry import build_tools

_WORKER_NODES = {
    "intake": intake_node,
    "account_servicing": account_servicing_node,
    "dispute": dispute_node,
    "product_info": product_info_node,
}


_REFUSAL_MESSAGES = {
    "prompt_injection_detected": (
        "I can't follow instructions embedded in a message like that. "
        "How can I help with your banking request?"
    ),
    "cross_customer_reference": (
        "I can only help with your own account. If this is about another "
        "customer, please contact us directly."
    ),
    "input_too_long": "That message is too long for me to process — could you summarize your request?",
}
_DEFAULT_REFUSAL = "I'm not able to help with that request. A human agent can assist further."


def _safe_refusal_message(reason_code: str | None) -> str:
    return _REFUSAL_MESSAGES.get(reason_code, _DEFAULT_REFUSAL)


async def ingress_input_guard_node(state: dict[str, Any]) -> dict[str, Any]:
    """Sanitize + evaluate the latest customer message before routing (P4-09):
    PII is masked (D-10); injection, cross-customer or overlong input is
    blocked outright with a safe refusal, short-circuiting straight to
    finalize without ever reaching the supervisor or a worker."""
    from src.guardrails.audit import record_action
    from src.guardrails.ingress import sanitize_ingress
    from src.guardrails.input import evaluate_input

    text = latest_user_text(state)
    customer_id = state["customer_id"]

    ingress_result = sanitize_ingress(text)
    sanitized_text = ingress_result["sanitized_text"]
    update: dict[str, Any] = {
        "ingress": {"sanitized_text": sanitized_text, "had_pii": ingress_result["had_pii"]}
    }

    if ingress_result["had_pii"]:
        record_action(
            actor="input_guard",
            action="sanitize_input",
            decision="sanitized",
            reason_code="pii_detected",
            customer_id=customer_id,
            details={"entity_types": [d["entity_type"] for d in ingress_result["detections"]]},
        )

    # Use the RAW text here, not sanitized_text: sanitize_ingress() already
    # masked any CUSTOMER_ID mention (e.g. "C0002" -> "<CUSTOMER_ID>"), which
    # would destroy the evidence detect_cross_customer_reference() needs to
    # compare against the authenticated customer id (real bug, found live).
    input_result = evaluate_input(text, authenticated_customer_id=customer_id)
    if input_result["decision"] == "block":
        record_action(
            actor="input_guard",
            action="block_input",
            decision="blocked",
            reason_code=input_result["reason_code"],
            customer_id=customer_id,
            details=input_result["details"],
        )
        update["route"] = "finalize"
        update["requires_human_review"] = True
        update["worker_results"] = [
            {
                "worker": "input_guard",
                "content": _safe_refusal_message(input_result["reason_code"]),
                "citations": [],
                "requires_human_review": True,
            }
        ]
    return update


def route_after_input_guard(state: dict[str, Any]) -> str:
    """Pure conditional-edge function: blocked input skips straight to
    finalize; everything else continues into the normal graph flow."""
    return "finalize" if state.get("route") == "finalize" else "continue"


async def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Package the final answer: applies the output guardrail (mask any
    leaked PAN/account, block another customer's id, rewrite refund/approval
    promises) and the output-risk classifier (a backstop human-review gate)
    before returning (P4-09)."""
    from src.guardrails.audit import record_action
    from src.guardrails.output import sanitize_output
    from src.guardrails.output_risk import classify_and_gate

    results = state.get("worker_results", [])
    escalated = bool(state.get("escalated"))
    customer_id = state.get("customer_id", "")

    if results:
        worker = results[-1]["worker"]
        content = results[-1]["content"]
        citations = results[-1].get("citations", [])
        requires_human = bool(results[-1].get("requires_human_review") or state.get("requires_human_review"))
    elif escalated:
        worker = "escalate_human"
        content = "This request needs a human banking agent, who will follow up."
        citations = []
        requires_human = True
    else:
        worker = "escalate_human"
        content = "I couldn't complete that request. Let me connect you to a human agent."
        citations = []
        requires_human = True

    output_result = sanitize_output(content, authenticated_customer_id=customer_id)
    content = output_result["sanitized_text"]
    if output_result["other_customer_blocked"] or output_result["refund_rewrites"] or output_result["system_prompt_leak_detected"]:
        record_action(
            actor="output_guard",
            action="sanitize_output",
            decision="sanitized",
            customer_id=customer_id,
            details={
                "other_customer_blocked": output_result["other_customer_blocked"],
                "refund_rewrites": bool(output_result["refund_rewrites"]),
                "system_prompt_leak_detected": output_result["system_prompt_leak_detected"],
            },
        )

    risk_result = classify_and_gate(worker, content, requires_human_review=requires_human)
    risk_tier = risk_result["risk_tier"]
    requires_human = risk_result["requires_human_review"]

    record_action(
        actor="finalize",
        action="finalize_answer",
        decision=risk_tier,
        reason_code=worker,
        customer_id=customer_id,
        details={"requires_human_review": requires_human},
    )

    final = FinalAnswer(
        answer=content,
        citations=citations,
        requires_human_review=requires_human,
        risk_tier=risk_tier,
        escalated=escalated,
    )
    return {"final_answer": final.model_dump(), "messages": [AIMessage(content=content)]}


async def load_memory_node(state: dict[str, Any], *, memory_store: Any) -> dict[str, Any]:
    """Recall relevant long-term memories for this customer (§7.1 Tiered memory,
    AC-05 return-visit recall)."""
    from src.memory.long_term import recall

    query = latest_user_text(state)
    recalled = await recall(memory_store, state["customer_id"], query, limit=5) if query else []
    return {"memory": {"recalled": recalled}}


async def build_context_node(state: dict[str, Any], *, summarizer_llm: Any) -> dict[str, Any]:
    """Select + compress the context available to whichever worker runs next
    (§7.1 Context engineering): summarize older turns if the conversation has
    grown long, then pick what fits a token budget."""
    messages = await maybe_summarize(summarizer_llm, state.get("messages", []))
    memories = state.get("memory", {}).get("recalled", [])
    selected = select_context(messages, memories=memories, tool_results=state.get("worker_results", []))
    return {
        "context": {
            "messages": selected.messages,
            "memories": selected.memories,
            "tool_results": selected.tool_results,
            "estimated_tokens": selected.estimated_tokens,
        }
    }


async def save_memory_node(state: dict[str, Any], *, memory_extractor: Any) -> dict[str, Any]:
    """Extract and persist durable facts from this conversation (§7.1 Tiered
    memory) so a return visit can recall them via load_memory_node.

    Runs AFTER finalize_node, so its only job from here is a best-effort
    memory write -- the customer-facing answer is already decided. A failure
    here must never destroy that answer: real incident found live (FA-03) --
    LangMem's extractor raised (observed as both a pydantic validation error
    and, separately, a GraphRecursionError from its own internal graph), and
    since save_memory_node had no error handling, that exception propagated
    up through graph.ainvoke() and was caught by cli.py's _invoke_turn generic
    GraphRecursionError handler, which discarded the already-correct finalize
    answer and returned the generic "took too many steps" fallback instead."""
    from src.memory.long_term import extract_and_store

    messages = state.get("messages", [])
    if messages and memory_extractor is not None:
        try:
            await extract_and_store(memory_extractor, state["customer_id"], messages)
        except Exception:  # noqa: BLE001 - best-effort; never sacrifice a good answer for this
            pass
    return {}


def build_graph(
    *,
    supervisor_llm: Any,
    worker_llm: Any,
    tools: list[Any],
    checkpointer: Any = None,
    memory_store: Any = None,
    memory_extractor: Any = None,
    summarizer_llm: Any = None,
):
    """Build and compile the copilot graph with injected models and tools.

    memory_store/memory_extractor are optional: when omitted (the default —
    every existing test does this), the graph behaves exactly as before
    (supervisor runs first, finalize ends the graph). When a memory_store is
    given, load_memory -> build_context wrap the front of the graph and
    save_memory wraps the end, wiring the tiered-memory pipeline in without
    changing behaviour for callers that don't need it.
    """
    g = StateGraph(CopilotState)

    # Ingress + input guard: always wired in, not opt-in (AC-06/AC-10 are
    # security requirements, unlike the memory pipeline's opt-in feature).
    g.add_node("input_guard", ingress_input_guard_node)
    g.add_node("supervisor", partial(supervisor_node, llm=supervisor_llm))
    for name, fn in _WORKER_NODES.items():
        # Every tool is routed through the registry (resilience + logging,
        # P3-07) tagged with this worker's name — no tool call can bypass
        # logs/tool_calls.jsonl by going around it.
        g.add_node(name, partial(fn, tools=build_tools(name, tools), llm=worker_llm))
    g.add_node("escalate_human", escalate_node)
    g.add_node("finalize", finalize_node)

    memory_enabled = memory_store is not None
    if memory_enabled:
        g.add_node("load_memory", partial(load_memory_node, memory_store=memory_store))
        g.add_node(
            "build_context", partial(build_context_node, summarizer_llm=summarizer_llm or worker_llm)
        )
        g.add_node("save_memory", partial(save_memory_node, memory_extractor=memory_extractor))

    g.add_edge(START, "input_guard")
    g.add_conditional_edges(
        "input_guard",
        route_after_input_guard,
        {"finalize": "finalize", "continue": "load_memory" if memory_enabled else "supervisor"},
    )
    if memory_enabled:
        g.add_edge("load_memory", "build_context")
        g.add_edge("build_context", "supervisor")

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

    if memory_enabled:
        g.add_edge("finalize", "save_memory")
        g.add_edge("save_memory", END)
    else:
        g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer)


@asynccontextmanager
async def open_checkpointer(conn_string: str | None = None) -> AsyncIterator[Any]:
    """Async context manager yielding an AsyncSqliteSaver.

    Defaults to STATE_DIR/checkpoints.sqlite (gitignored) so short-term thread
    state persists across turns without ever being committed. Tests that need
    an isolated store should pass an explicit conn_string (e.g. a pytest
    tmp_path) rather than monkeypatching STATE_DIR — `settings` is a
    module-level singleton resolved once at import time, so an env var set
    later in a test has no effect on it (verified: a monkeypatch-only test
    silently shared the real data/state/checkpoints.sqlite file and leaked
    state across pytest runs on a reused thread id).
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    settings.ensure_dirs()
    conn = conn_string or str(settings.state_dir / "checkpoints.sqlite")
    async with AsyncSqliteSaver.from_conn_string(conn) as saver:
        yield saver


def run_config(thread_id: str) -> dict[str, Any]:
    """Invoke config: the checkpointer thread id and the recursion limit (NFR-04)."""
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.recursion_limit,
    }
