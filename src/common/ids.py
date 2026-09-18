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

import uuid


def new_run_id() -> str:
    """A fresh run_id: one per conversation run (one CLI chat/run invocation)."""
    return f"run-{uuid.uuid4()}"
