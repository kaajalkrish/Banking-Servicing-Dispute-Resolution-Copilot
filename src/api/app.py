"""Async FastAPI streaming endpoint (ref-doc.md §7.7 Bonus, §8.1, §4 Interface).

    POST /chat/stream   server-sent events for one customer turn
    GET  /health        liveness; no model call

This is a bonus interface: the CLI (src/cli.py) remains the required one, and
there is no web front end. The endpoint reuses the CLI's graph
(``build_graph``), tool loader, tracing and audit, so the ingress mask, input
and output guards, risk gate and tool-scope gateway all apply identically;
see src/api/streaming.py for the event protocol and its design decisions.

**Authentication is not implemented.** The endpoint trusts the ``customer_id``
it is given, exactly as the CLI's ``--customer-id`` does. Anyone who can reach
it can act as any customer, so it binds to loopback by default and must not
be exposed until real authentication is added (docs/security-approach.md).

Run: ``python -m src.api`` (API_HOST / API_PORT / API_TURN_TIMEOUT_S).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.api.streaming import stream_turn
from src.common.ids import new_run_id
from src.config import settings
from src.guardrails.input import MAX_INPUT_LENGTH


class ChatRequest(BaseModel):
    customer_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    # The input guard enforces the same length cap with a safe refusal; the API
    # rejects oversized bodies earlier, before any graph work.
    message: str = Field(min_length=1, max_length=MAX_INPUT_LENGTH)
    # No ':' allowed: the server prefixes the customer id with one, so a client
    # cannot forge another customer's thread id.
    thread_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,64}$")

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


def create_app(graph: Any | None = None, *, turn_timeout_s: float | None = None) -> FastAPI:
    """Build the app. ``graph`` is for tests: pass a compiled (or fake) graph
    to skip the real Gemini/MCP/checkpointer start-up."""
    timeout_s = settings.api_turn_timeout_s if turn_timeout_s is None else turn_timeout_s

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.graph is not None:
            yield
            return

        from src.cli import _load_tools
        from src.graph import build_graph, open_checkpointer
        from src.llm import get_llm
        from src.memory.long_term import build_extractor, open_memory_store
        from src.observability.tracing import flush_tracing, init_tracing

        settings.require_api_key()  # fail fast with a clear message if unset
        init_tracing()  # called on the run path (not merely imported), as in the CLI
        tools = await _load_tools()
        worker_llm = get_llm("default")
        async with open_checkpointer() as saver, open_memory_store() as mstore:
            app.state.graph = build_graph(
                supervisor_llm=get_llm("fast"),
                worker_llm=worker_llm,
                tools=tools,
                checkpointer=saver,
                memory_store=mstore,
                memory_extractor=build_extractor(worker_llm, mstore),
            )
            try:
                yield
            finally:
                flush_tracing()

    app = FastAPI(title="Banking Servicing Copilot (streaming bonus)", lifespan=lifespan)
    app.state.graph = graph

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "graph_ready": app.state.graph is not None}

    @app.post("/chat/stream")
    async def chat_stream(req: ChatRequest) -> StreamingResponse:
        if app.state.graph is None:
            raise HTTPException(status_code=503, detail="copilot is not ready")
        return StreamingResponse(
            stream_turn(
                app.state.graph,
                customer_id=req.customer_id,
                message=req.message,
                thread_id=req.thread_id,
                run_id=new_run_id(),
                timeout_s=timeout_s,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
