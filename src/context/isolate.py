"""Context-engineering: ISOLATE strategy (§7.1 Context engineering).

Gives each worker only the slice of state it actually needs, rather than the
full graph state — a worker cannot see fields it has no reason to use (e.g.
product_info never sees another worker's dispute draft), which keeps prompts
smaller and reduces the chance one worker's output leaks into another's
reasoning.
"""

from __future__ import annotations

from typing import Any

# The state keys each worker is allowed to see, beyond the always-included
# core fields (customer_id, messages).
_WORKER_FIELD_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "account_servicing": ("account_ref",),
    "dispute": ("account_ref",),
    "product_info": (),
    "intake": (),
    "escalate_human": (),
}

_CORE_FIELDS = ("customer_id", "messages", "context", "ingress")


def isolate_for_worker(state: dict[str, Any], worker: str) -> dict[str, Any]:
    """Return the reduced state slice a worker should see."""
    allowed = set(_CORE_FIELDS) | set(_WORKER_FIELD_ALLOWLIST.get(worker, ()))
    return {k: v for k, v in state.items() if k in allowed}
