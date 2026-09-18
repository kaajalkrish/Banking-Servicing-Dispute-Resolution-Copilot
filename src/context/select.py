"""Context-engineering: SELECT strategy (§7.1 Context engineering).

Picks the recent turns, recalled memories and tool results that fit within a
token budget, so the prompt sent to a worker stays bounded regardless of how
long a conversation or how large a tool result gets. Token counts are
estimated with a simple character-based heuristic (no tokenizer dependency);
being approximate is fine here since this only sizes a budget, not a hard API
limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ~4 characters per token is a standard rough estimate for English text.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class SelectedContext:
    messages: list[Any] = field(default_factory=list)
    memories: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    estimated_tokens: int = 0


def message_text(msg: Any) -> str:
    """Extract a message's text content as a plain string (public helper; also
    used by src/context/summarization.py)."""
    content = getattr(msg, "content", msg)
    return content if isinstance(content, str) else str(content)


def select_context(
    messages: list[Any],
    memories: list[str] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    *,
    token_budget: int = 2000,
    keep_last_turns: int = 6,
) -> SelectedContext:
    """Select what fits the budget, always keeping the most recent turns verbatim.

    Priority order (most important first): the last `keep_last_turns` messages,
    then recalled memories (short, high-value), then tool results (often the
    largest and least essential once summarized elsewhere).
    """
    memories = memories or []
    tool_results = tool_results or []

    recent = messages[-keep_last_turns:] if keep_last_turns > 0 else []
    budget = token_budget
    out = SelectedContext()

    for msg in recent:
        out.messages.append(msg)
        budget -= estimate_tokens(message_text(msg))

    for mem in memories:
        cost = estimate_tokens(mem)
        if cost > budget:
            break
        out.memories.append(mem)
        budget -= cost

    for result in tool_results:
        cost = estimate_tokens(str(result))
        if cost > budget:
            break
        out.tool_results.append(result)
        budget -= cost

    out.estimated_tokens = token_budget - budget
    return out
