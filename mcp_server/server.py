"""Custom MCP server (MCP Python SDK, stdio) exposing banking servicing tools.

Exposes 6 tools and 1 resource (ref-doc.md §7.1 requires >=2 tools + 1 resource):
    tools     : get_account_balance, list_recent_transactions, get_statement_summary,
                create_dispute_case, get_dispute_status, submit_service_request
    resource  : bank://reference/dispute-windows

Rules honoured here:
- stdio transport: NOTHING is ever written to stdout except MCP protocol frames
  (no print()); all diagnostics go to files via the transcript layer (P1-07).
- Every returned value is already masked by data_access (NFR-05, AC-06).
- Tools return structured error objects instead of leaking stack traces.
- Dispute cases are created as drafts only; the copilot never resolves money
  movement (D-13).

Run standalone:  python -m mcp_server.server
"""

from __future__ import annotations

import functools
import inspect
import json
import time
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from mcp_server.data_access import DISPUTE_WINDOWS, Bank
from mcp_server.transcript import record

mcp = FastMCP("bank-servicing")
_bank = Bank()

_KNOWN_ERRORS = (LookupError, ValueError, PermissionError)


def _safe(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Turn known domain errors into structured errors AND transcript every call."""
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            call_args = dict(bound.arguments)
        except TypeError:
            call_args = {"args": list(args), "kwargs": kwargs}
        start = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except _KNOWN_ERRORS as exc:
            result = {"error": {"type": type(exc).__name__, "message": str(exc)}}
        latency_ms = (time.perf_counter() - start) * 1000
        status = "error" if isinstance(result, dict) and "error" in result else "ok"
        record("tools/call", fn.__name__, call_args, result, latency_ms, status)
        return result

    return wrapper


@mcp.tool()
@_safe
def get_account_balance(customer_id: str, account_ref: str | None = None) -> dict:
    """Return the current balance for the authenticated customer's account.

    account_ref is the last 4 digits of the account; omit if the customer has
    a single account.
    """
    return _bank.account_balance(customer_id, account_ref)


@mcp.tool()
@_safe
def list_recent_transactions(
    customer_id: str, account_ref: str | None = None, limit: int = 10
) -> dict:
    """List the most recent transactions (default 10, max 50) for an account."""
    return _bank.recent_transactions(customer_id, account_ref, limit)


@mcp.tool()
@_safe
def get_statement_summary(customer_id: str, account_ref: str | None = None) -> dict:
    """Summarise an account: transaction count, total spend and spend by category."""
    return _bank.statement_summary(customer_id, account_ref)


@mcp.tool()
@_safe
def create_dispute_case(
    customer_id: str, transaction_id: str, reason: str, description: str = ""
) -> dict:
    """Open a DRAFT dispute case for a transaction (never auto-resolved)."""
    return _bank.create_dispute(customer_id, transaction_id, reason, description)


@mcp.tool()
@_safe
def get_dispute_status(dispute_id: str) -> dict:
    """Return the status of an existing dispute case."""
    return _bank.dispute_status(dispute_id)


@mcp.tool()
@_safe
def check_dispute_eligibility(customer_id: str, transaction_id: str, reason: str) -> dict:
    """Check dispute eligibility for a transaction against the dispute-windows
    reference (deterministic: window days, transaction status, already-disputed).
    reason must be one of: unrecognized_charge, unauthorized_transaction,
    duplicate_charge, goods_not_received, billing_error.
    """
    return _bank.check_dispute_eligibility(customer_id, transaction_id, reason)


@mcp.tool()
@_safe
def submit_service_request(customer_id: str, request_type: str, details: str = "") -> dict:
    """Submit a simple service request: card_replacement, statement_copy or limit_change."""
    return _bank.submit_service_request(customer_id, request_type, details)


@mcp.resource("bank://reference/dispute-windows")
def dispute_windows() -> str:
    """Servicing reference: dispute eligibility windows (in days) by reason."""
    start = time.perf_counter()
    payload = json.dumps(DISPUTE_WINDOWS, indent=2)
    record(
        "resources/read",
        "bank://reference/dispute-windows",
        {},
        DISPUTE_WINDOWS,
        (time.perf_counter() - start) * 1000,
        "ok",
    )
    return payload


if __name__ == "__main__":
    mcp.run()
