"""Shared helpers for worker agents."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm import ainvoke_with_backoff


def extract_text(content: Any) -> str:
    """Normalize a chat message's content to plain text.

    Older Gemini models return a plain string. Gemini 3.x returns a list of
    content-part dicts (``[{'type': 'text', 'text': ..., 'extras': {...}}]``,
    the 'extras' carrying an internal signature blob we must never surface).
    This extracts and concatenates just the text parts.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
            elif isinstance(part, str):
                parts.append(part)
        if parts:
            return "".join(parts)
    return str(content)


def latest_user_text(state: dict[str, Any]) -> str:
    """Return the text of the most recent human message.

    If ingress sanitization has run (graph.py's ingress_input_guard_node,
    P4-09), the SANITIZED version is preferred so no downstream code
    (worker prompts, tracing, tool_calls.jsonl) ever sees the raw,
    PII-containing text (D-10). Falls back to the raw message when no
    ingress step has run (e.g. a test building state directly)."""
    sanitized = state.get("ingress", {}).get("sanitized_text")
    if sanitized is not None:
        return sanitized
    for msg in reversed(state.get("messages", [])):
        # HumanMessage has type 'human'; be lenient about message representation.
        if getattr(msg, "type", None) == "human" or msg.__class__.__name__ == "HumanMessage":
            content = getattr(msg, "content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def get_tool(
    tools: list[Any], name: str, *, authenticated_customer_id: str | None = None
) -> Any | None:
    """Find a tool by name. When authenticated_customer_id is given, the tool
    is wrapped in a ScopeGatewayTool (P4-05) — defense-in-depth: a customer_id
    argument that ever mismatches the authenticated one is denied and audited,
    never silently let through."""
    for t in tools:
        if getattr(t, "name", None) == name:
            if authenticated_customer_id is None:
                return t
            from src.guardrails.audit import record_action
            from src.tools.gateway import ScopeGatewayTool

            def _on_denied(tool_name: str, auth_id: str, requested_id: str) -> None:
                record_action(
                    actor="gateway",
                    action="tool_call",
                    decision="denied",
                    tool=tool_name,
                    reason_code="cross_customer_scope_violation",
                    customer_id=auth_id,
                    details={"requested_customer_id": requested_id},
                )

            return ScopeGatewayTool(t, authenticated_customer_id=authenticated_customer_id, on_denied=_on_denied)
    return None


def memory_context_block(state: dict[str, Any]) -> str:
    """Format recalled long-term memories (built by graph.py's build_context_node
    from src/context/select.py) as a short block for an LLM prompt, or "" if
    there is nothing recalled for this turn."""
    memories = state.get("context", {}).get("memories", [])
    if not memories:
        return ""
    bullet_list = "\n".join(f"- {m}" for m in memories)
    return f"\nKnown context about this customer from prior sessions:\n{bullet_list}\n"


async def compose_answer(llm: Any, system: str, human: str) -> str:
    """One LLM call to phrase an answer from tool context.

    Retries transient errors (timeouts/429/5xx) via ainvoke_with_backoff so a
    momentary Gemini hiccup degrades gracefully instead of crashing the run
    (NFR-04), and normalizes the response content across model versions.
    """
    resp = await ainvoke_with_backoff(
        llm, [SystemMessage(content=system), HumanMessage(content=human)]
    )
    return extract_text(getattr(resp, "content", resp))


def record_result(
    state: dict[str, Any],
    worker: str,
    content: str,
    *,
    requires_human_review: bool = False,
    citations: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a state update appending this worker's result."""
    results = list(state.get("worker_results", []))
    results.append(
        {
            "worker": worker,
            "content": content,
            "citations": citations or [],
            "requires_human_review": requires_human_review,
        }
    )
    update: dict[str, Any] = {"worker_results": results}
    if requires_human_review:
        update["requires_human_review"] = True
    return update
