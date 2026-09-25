"""Short-term (thread-scoped) memory (§7.1 Tiered memory).

The LangGraph SQLite checkpointer (src/graph.py's AsyncSqliteSaver) already
persists the full graph state per thread_id across turns, which is how facts
stated earlier in a conversation carry forward (AC-05). This module is a thin,
testable read API over that persisted state, verified against the installed
checkpointer's real CheckpointTuple shape (checkpoint['channel_values']), so
context selection (src/context/select.py) has an easy way to pull prior turns
without duplicating storage.
"""

from __future__ import annotations

from typing import Any

from src.graph import run_config


async def get_thread_state(checkpointer: Any, thread_id: str) -> dict[str, Any]:
    """Return the persisted channel_values for a thread, or {} if none yet."""
    checkpoint_tuple = await checkpointer.aget_tuple(run_config(thread_id))
    if checkpoint_tuple is None:
        return {}
    return dict(checkpoint_tuple.checkpoint.get("channel_values", {}))


async def get_thread_messages(checkpointer: Any, thread_id: str) -> list[Any]:
    """Return the message history recorded for a thread, oldest first."""
    state = await get_thread_state(checkpointer, thread_id)
    return list(state.get("messages", []))


async def has_prior_turns(checkpointer: Any, thread_id: str) -> bool:
    return len(await get_thread_messages(checkpointer, thread_id)) > 0
