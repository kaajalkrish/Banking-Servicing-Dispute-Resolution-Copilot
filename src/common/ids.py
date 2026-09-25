"""Run/session id helpers (§7.2 Phoenix instrumentation, D-04).

Phoenix/OpenTelemetry natively expose trace_id and span_id, but nothing that
identifies "one conversation run" the way this project needs for citations
(AC-08: "Phoenix run_id + span_id"). ``new_run_id()`` mints our own id, which
the tracing layer stamps as a span attribute (``metadata.run_id`` and
``session.id``) on every span, and which is written into ``tool_calls.jsonl``
and ``agent_actions.jsonl`` — so a failure-analysis citation of
run_id + trace_id + span_id can be resolved back to a committed artifact
regardless of which of the three identifiers is easiest to search by.
"""

from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import Iterator


def new_run_id() -> str:
    """A fresh run_id: one per conversation run (one CLI chat/run invocation)."""
    return f"run-{uuid.uuid4()}"


_current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_run_id", default=None
)


def get_current_run_id() -> str | None:
    """The run_id of the currently-executing bind_run_id()/traced_run() scope,
    or None outside one."""
    return _current_run_id.get()


@contextmanager
def bind_run_id(run_id: str) -> Iterator[None]:
    """Make run_id available to get_current_run_id() for this context,
    independent of whether Phoenix tracing is enabled — so committed evidence
    like logs/tool_calls.jsonl always carries a real run_id even if
    PHOENIX_ENABLED=false. src.observability.tracing.traced_run() wraps this
    and additionally stamps the OTel session/metadata attributes."""
    token = _current_run_id.set(run_id)
    try:
        yield
    finally:
        _current_run_id.reset(token)
