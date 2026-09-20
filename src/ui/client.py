"""HTTP client for the optional Streamlit UI (src/ui/app.py).

The UI is a thin client of the streaming API (``python -m src.api``): it never
imports the graph, so the input guard, output guard, risk gate, tool-scope
gateway, tracing and audit all apply exactly as they do for the CLI and the API.
This module holds everything that is not drawing widgets, so it can be tested
without Streamlit.

Protocol (see src/api/streaming.py): ``POST /chat/stream`` returns
server-sent events ``start`` / ``progress`` / ``error`` / ``final``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8000"
_CUSTOMERS_PATH = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "customers.json"


class ApiError(RuntimeError):
    """The API could not be reached, or rejected the request. The message is
    safe to show to a customer: it never carries a response body verbatim."""


def iter_sse(lines: Iterable[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(event, data)`` for each server-sent event as its blank line
    arrives, so a caller can show progress while the turn is still running."""
    event: str | None = None
    data: list[str] = []
    for line in lines:
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data.append(line[6:])
        elif line == "" and event is not None:
            yield event, (json.loads("\n".join(data)) if data else {})
            event, data = None, []


def new_thread_id() -> str:
    """A conversation id the API accepts (letters, digits, ``_``, ``.``, ``-``).
    The server prefixes it with the customer id, so it cannot address another
    customer's history."""
    return f"ui-{uuid.uuid4().hex[:12]}"


def load_customers(path: Path = _CUSTOMERS_PATH) -> list[tuple[str, str]]:
    """``[(customer_id, display_name)]`` of the synthetic customers."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [(r["customer_id"], r.get("name", r["customer_id"])) for r in rows]


def api_health(base_url: str, *, timeout: float = 2.0, http_client: httpx.Client | None = None) -> dict[str, Any] | None:
    """``/health`` as a dict, or None if the API is not reachable."""
    try:
        if http_client is not None:
            resp = http_client.get("/health")
        else:
            resp = httpx.get(f"{base_url.rstrip('/')}/health", timeout=timeout)
        return resp.json() if resp.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _rejection_message(resp: httpx.Response) -> str:
    if resp.status_code == 422:
        return "The request was not accepted (check the customer and message)."
    if resp.status_code == 503:
        return "The copilot is not ready yet. Try again in a moment."
    return f"The copilot returned an unexpected response (HTTP {resp.status_code})."


def stream_chat(
    base_url: str,
    customer_id: str,
    message: str,
    thread_id: str,
    *,
    timeout: float = 150.0,
    http_client: httpx.Client | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Send one turn and yield the API's events as they arrive.

    ``http_client`` is for tests (a FastAPI ``TestClient`` is an ``httpx.Client``).
    Raises ``ApiError`` for an unreachable API, a timeout or a rejected request.
    """
    owns_client = http_client is None
    http = http_client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
    body = {"customer_id": customer_id, "message": message, "thread_id": thread_id}
    try:
        with http.stream("POST", "/chat/stream", json=body) as resp:
            if resp.status_code != 200:
                resp.read()
                raise ApiError(_rejection_message(resp))
            yield from iter_sse(resp.iter_lines())
    except httpx.ConnectError as exc:
        raise ApiError(f"Cannot reach the copilot API at {base_url}. Start it with: python -m src.api") from exc
    except httpx.TimeoutException as exc:
        raise ApiError("The copilot took too long to answer.") from exc
    except httpx.HTTPError as exc:
        raise ApiError("The connection to the copilot API failed.") from exc
    finally:
        if owns_client:
            http.close()
