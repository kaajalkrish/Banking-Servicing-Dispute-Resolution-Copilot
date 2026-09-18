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
    """Return the text of the most recent human message."""
    for msg in reversed(state.get("messages", [])):
        # HumanMessage has type 'human'; be lenient about message representation.
        if getattr(msg, "type", None) == "human" or msg.__class__.__name__ == "HumanMessage":
            content = getattr(msg, "content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def get_tool(tools: list[Any], name: str) -> Any | None:
    for t in tools:
        if getattr(t, "name", None) == name:
            return t
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
