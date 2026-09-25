"""Tool gateway: enforce authenticated customer scope at every tool call (AC-06).

Defense-in-depth. Every worker already reads ``customer_id`` from state
(never from LLM output — see ``isolate_for_worker``), so a customer cannot
read another customer's data through normal operation. This gateway is the
back-stop: if a tool call's ``customer_id`` argument ever mismatches the
authenticated one — a future bug in a worker, a manipulated extraction,
anything — the call is DENIED, never silently corrected and let through, so
the mismatch is visible (and, once wired into the graph in P4-09, audited)
rather than quietly masked by a "helpful" override.
"""

from __future__ import annotations

from typing import Any, Callable

DENIAL_REASON = "cross_customer_scope_violation"


def scope_denial(tool_name: str, authenticated_id: str, requested_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": tool_name,
        "error": {
            "type": "PermissionError",
            "message": (
                f"Tool call denied: customer_id {requested_id!r} does not match "
                f"the authenticated customer {authenticated_id!r}."
            ),
            "reason_code": DENIAL_REASON,
        },
    }


class ScopeGatewayTool:
    """Wraps a tool so a ``customer_id`` arg mismatching the authenticated
    customer is denied before the underlying tool ever runs. Tools with no
    ``customer_id`` argument (e.g. ``get_dispute_status``, ``policy_search``)
    pass through unchanged."""

    def __init__(
        self,
        tool: Any,
        *,
        authenticated_customer_id: str,
        on_denied: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._tool = tool
        self.name = getattr(tool, "name", getattr(tool, "__name__", "tool"))
        self._authenticated_id = authenticated_customer_id
        self._on_denied = on_denied

    async def ainvoke(self, args: dict[str, Any]) -> Any:
        requested_id = args.get("customer_id")
        if requested_id is not None and requested_id != self._authenticated_id:
            if self._on_denied is not None:
                self._on_denied(self.name, self._authenticated_id, requested_id)
            return scope_denial(self.name, self._authenticated_id, requested_id)
        return await self._tool.ainvoke(args)
