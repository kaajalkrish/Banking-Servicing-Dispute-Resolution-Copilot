"""Streaming turn runner for the FastAPI bonus endpoint (ref-doc.md §7.7 Bonus,
§8.1).

Runs one customer turn through the SAME compiled graph the CLI uses, so the
ingress mask, input guard, output guard, risk gate, tool-scope gateway and
audit trail all apply unchanged, and the turn is traced under its own run_id.
What this module adds is only the transport: server-sent events.

Events (each ``event: <name>`` + one JSON ``data:`` line):

- ``start``    -- run_id, the client's thread_id and the AI disclosure
                  (AI Act Art. 50(1)/(5): shown at the first interaction).
- ``progress`` -- ``{"node": <name>}`` as each graph node finishes.
- ``error``    -- only on failure: ``{"type": ...}``, a fixed message, never an
                  exception string.
- ``final``    -- the answer, after the output guard and risk gate.

Design decisions:

- **Only node names stream while the turn runs, never node content.** A
  worker's draft has not yet passed ``finalize``'s output guard (PAN/account
  masking, refund-promise rewrite, system-prompt-leak redaction) or the
  human-review gate, so streaming it would bypass those controls. The
  customer sees exactly one answer: the one ``finalize`` produced.
- **Thread ids are namespaced by customer** (``<customer_id>:<thread_id>``).
  The checkpointer keys conversation history by thread id, so an
  attacker-chosen thread id must not be able to load another customer's
  history.
- **Failure degrades to a safe, escalated final answer** (NFR-04): hitting
  the recursion limit, the per-turn timeout, or any other error ends the
  stream with a human-review answer instead of a broken connection.
- The timeout covers the whole turn including time a slow client takes to read.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from langgraph.errors import GraphRecursionError

from src.cli import recursion_fallback_state
from src.common.disclosure import AI_DISCLOSURE
from src.common.masking import mask_obj
from src.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT_MESSAGE = (
    "This request needs a human banking agent: it took too long to process automatically."
)
_ERROR_MESSAGE = (
    "This request needs a human banking agent: something went wrong while processing it."
)


def sse(event: str, data: dict[str, Any]) -> str:
    """Format one server-sent event. ``data`` is JSON on a single line."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def scoped_thread_id(customer_id: str, thread_id: str | None) -> str:
    """Checkpointer thread id, namespaced so customers cannot share history."""
    return f"{customer_id}:{thread_id or 'default'}"


def _escalated(message: str) -> dict[str, Any]:
    return {
        "answer": message,
        "citations": [],
        "requires_human_review": True,
        "risk_tier": "high",
        "escalated": True,
    }


async def stream_turn(
    graph: Any,
    *,
    customer_id: str,
    message: str,
    thread_id: str | None,
    run_id: str,
    timeout_s: float,
    trace: Any = None,
) -> AsyncIterator[str]:
    """Yield the SSE frames for one turn. Never raises: every failure ends in
    an ``error`` frame followed by a safe ``final`` frame."""
    from src.graph import run_config
    from src.observability.tracing import traced_run
    from src.state import new_state

    trace = trace or traced_run
    yield sse(
        "start",
        {"run_id": run_id, "thread_id": thread_id or "default", "disclosure": AI_DISCLOSURE},
    )

    final: dict[str, Any] | None = None
    error_type: str | None = None
    try:
        with trace(run_id):
            async with asyncio.timeout(timeout_s):
                state = new_state(customer_id, message, max_steps=settings.max_steps)
                config = run_config(scoped_thread_id(customer_id, thread_id))
                async for chunk in graph.astream(state, config, stream_mode="updates"):
                    for node, update in chunk.items():
                        yield sse("progress", {"node": node})
                        if node == "finalize" and isinstance(update, dict) and update.get("final_answer"):
                            final = update["final_answer"]
    except GraphRecursionError:
        error_type, final = "recursion_limit", recursion_fallback_state()["final_answer"]
    except TimeoutError:
        error_type, final = "timeout", _escalated(_TIMEOUT_MESSAGE)
    except Exception as exc:  # noqa: BLE001 -- a stream must end cleanly, whatever failed
        # Log the exception type only: its message can carry customer text.
        logger.error("streaming turn %s failed: %s", run_id, type(exc).__name__)
        error_type, final = "internal_error", _escalated(_ERROR_MESSAGE)

    if final is None:  # graph finished without producing a finalize update
        error_type, final = "no_answer", _escalated(_ERROR_MESSAGE)

    if error_type is not None:
        yield sse("error", {"type": error_type})
    yield sse("final", mask_obj(final))
