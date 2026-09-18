"""Context-engineering: COMPRESS strategy (§7.1 Context engineering).

Trims/summarizes long tool outputs before they enter a prompt, so one verbose
tool result (e.g. 50 transactions) doesn't dominate the context window. Purely
deterministic — no LLM call — so it is cheap to run on every tool result.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_ITEMS = 5
DEFAULT_MAX_CHARS = 800


def compress_list(items: list[Any], max_items: int = DEFAULT_MAX_ITEMS) -> list[Any]:
    """Keep only the first max_items, noting how many were dropped."""
    if len(items) <= max_items:
        return items
    kept = list(items[:max_items])
    kept.append({"_truncated": True, "omitted_count": len(items) - max_items})
    return kept


def compress_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [truncated, {len(text) - max_chars} more characters]"


def compress_tool_result(
    result: Any, *, max_items: int = DEFAULT_MAX_ITEMS, max_chars: int = DEFAULT_MAX_CHARS
) -> Any:
    """Recursively compress a tool result: cap list lengths and string lengths.

    Dict values are compressed in place (new dict returned); the special keys
    used elsewhere (e.g. 'error') are passed through unchanged so downstream
    error-handling logic keeps working on compressed results.
    """
    if isinstance(result, dict):
        return {k: compress_tool_result(v, max_items=max_items, max_chars=max_chars) for k, v in result.items()}
    if isinstance(result, list):
        compressed = [compress_tool_result(v, max_items=max_items, max_chars=max_chars) for v in result]
        return compress_list(compressed, max_items=max_items)
    if isinstance(result, str):
        return compress_text(result, max_chars=max_chars)
    return result
