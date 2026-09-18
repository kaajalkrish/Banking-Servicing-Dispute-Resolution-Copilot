"""Shared helpers for worker agents."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

_TXN_RE = re.compile(r"\bTXN\d{3,}\b", re.IGNORECASE)


def latest_user_text(state: dict[str, Any]) -> str:
    """Return the text of the most recent human message."""
    for msg in reversed(state.get("messages", [])):
        # HumanMessage has type 'human'; be lenient about message representation.
        if getattr(msg, "type", None) == "human" or msg.__class__.__name__ == "HumanMessage":
            content = getattr(msg, "content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def find_transaction_id(text: str) -> str | None:
    m = _TXN_RE.search(text or "")
    return m.group(0).upper() if m else None


def get_tool(tools: list[Any], name: str) -> Any | None:
    for t in tools:
        if getattr(t, "name", None) == name:
            return t
    return None


async def compose_answer(llm: Any, system: str, human: str) -> str:
    """One structured-free LLM call to phrase an answer from tool context."""
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    content = getattr(resp, "content", resp)
    return content if isinstance(content, str) else str(content)


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
