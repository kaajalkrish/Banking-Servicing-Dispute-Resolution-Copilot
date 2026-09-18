"""Context-engineering: WRITE strategy (§7.1 Context engineering).

Persists durable, worth-remembering notes (a stated preference, a dispute
reference, the last topic discussed) to a long-term store so they survive past
the current turn/thread. The store is a minimal duck-typed interface — P2-11's
LangMem-backed store implements it — so this module has no hard dependency on
any particular memory backend and is fully offline-testable with a fake.
"""

from __future__ import annotations

from typing import Any, Protocol


class SupportsPut(Protocol):
    def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None: ...


def customer_namespace(customer_id: str) -> tuple[str, ...]:
    """Per-customer namespace so one customer's notes never leak into another's."""
    return ("customer_memory", customer_id)


def write_note(
    store: SupportsPut,
    customer_id: str,
    key: str,
    content: dict[str, Any],
) -> None:
    """Write one durable note (already masked by the caller) for a customer."""
    store.put(customer_namespace(customer_id), key, content)


def write_turn_summary_note(store: SupportsPut, customer_id: str, thread_id: str, summary: str) -> None:
    """Convenience: record what a conversation was about, keyed by thread."""
    write_note(store, customer_id, f"topic::{thread_id}", {"summary": summary})
