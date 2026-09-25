"""Context-engineering: WRITE strategy (§7.1 Context engineering).

Persists durable, worth-remembering notes (a stated preference, a dispute
reference, the last topic discussed) to a long-term store so they survive past
the current turn/thread. The store is a minimal duck-typed interface —
src/memory/long_term.py's AsyncSqliteStore-backed store implements it — so
this module has no hard dependency on any particular memory backend and is
fully offline-testable with a fake.

Note: an earlier version of this module assumed a sync ``store.put(...)``
method. The real LangGraph BaseStore API (verified against the installed
langgraph-checkpoint-sqlite's AsyncSqliteStore) is async — ``aput`` — so the
protocol and functions here are async to match reality (plan.md rule: follow
the installed API, not an assumption).
"""

from __future__ import annotations

from typing import Any, Protocol


class SupportsAPut(Protocol):
    async def aput(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None: ...


def customer_namespace(customer_id: str) -> tuple[str, ...]:
    """Per-customer namespace so one customer's notes never leak into another's."""
    return ("customer_memory", customer_id)


async def write_note(
    store: SupportsAPut,
    customer_id: str,
    key: str,
    content: dict[str, Any],
) -> None:
    """Write one durable note (already masked by the caller) for a customer."""
    await store.aput(customer_namespace(customer_id), key, content)


async def write_turn_summary_note(store: SupportsAPut, customer_id: str, thread_id: str, summary: str) -> None:
    """Convenience: record what a conversation was about, keyed by thread."""
    await write_note(store, customer_id, f"topic::{thread_id}", {"summary": summary})
