"""Arize Phoenix instrumentation (§7.2 Phoenix instrumentation, mandated).

``init_tracing()`` is idempotent: starts the local Phoenix app persisted to
``.phoenix/`` at the repo root (gitignored, D-07) so traces survive across CLI
runs, registers the OTel tracer provider, and auto-instruments LangChain via
openinference — so every graph run is traced automatically once this is
called on the run path (P3-05 calls it from the CLI before graph execution;
importing this module alone does nothing).

Verified against the installed ``arize-phoenix==14.6.0`` API, not assumed:
``px.launch_app(use_temp_dir=False)`` + the ``PHOENIX_WORKING_DIR`` env var for
persistence; ``register(auto_instrument=True)`` to pick up
``openinference-instrumentation-langchain`` automatically; and
``phoenix.client.Client(base_url=...).spans.get_spans_dataframe()`` for
reading spans back — **not** ``px.Client()``, which does not exist in this
version (a real smoke test with a live Gemini call round-tripped through this
exact path and confirmed a captured span: ``span_kind=LLM, status_code=OK``).

Can be disabled via ``PHOENIX_ENABLED=false`` — tests default to disabled
(see ``tests/conftest.py``), since spinning up a local web server per test run
would be slow and noisy.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from src.config import settings

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHOENIX_WORKING_DIR = _REPO_ROOT / ".phoenix"
PHOENIX_URL = "http://localhost:6006"

_state: dict[str, Any] = {"initialized": False, "tracer_provider": None, "session": None}


def init_tracing(project_name: str | None = None) -> Any | None:
    """Start Phoenix + register OTel tracing. Idempotent: only the first call
    in a process does any work; later calls return the same tracer provider.
    Returns None if PHOENIX_ENABLED=false."""
    if _state["initialized"]:
        return _state["tracer_provider"]
    _state["initialized"] = True

    if not settings.phoenix_enabled:
        return None

    import phoenix as px
    from phoenix.otel import register

    PHOENIX_WORKING_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PHOENIX_WORKING_DIR", str(PHOENIX_WORKING_DIR))

    _state["session"] = px.launch_app(use_temp_dir=False)
    _state["tracer_provider"] = register(
        project_name=project_name or settings.phoenix_project,
        auto_instrument=True,  # picks up openinference-instrumentation-langchain
        batch=False,  # spans are visible immediately; fine at our volume
    )
    return _state["tracer_provider"]


@contextmanager
def traced_run(run_id: str) -> Iterator[None]:
    """Stamp run_id on every span created within this context (D-04).

    Sets both ``using_session(run_id)`` and ``using_metadata({"run_id":
    run_id})``. Verified with two real end-to-end runs, not assumed: in
    isolation (no LangGraph thread_id in play), both ``attributes.session.id``
    and ``attributes.metadata.run_id`` come back set to run_id. Through the
    real CLI (a LangGraph checkpointer thread_id is in play),
    ``attributes.session.id`` is overridden to the conversation's thread_id
    instead — LangGraph's own instrumentation takes precedence there, which
    is arguably more useful anyway (it groups a whole conversation thread in
    Phoenix's UI). ``attributes.metadata.run_id`` reliably carries this
    run_id regardless, confirmed across 20 real spans from one CLI turn — so
    AC-08 citations should resolve run_id via ``metadata.run_id``, not
    ``session.id``.

    Also binds run_id to src.common.ids.get_current_run_id() (via bind_run_id)
    regardless of whether tracing is enabled, so tool_calls.jsonl still gets a
    real run_id even with PHOENIX_ENABLED=false."""
    from src.common.ids import bind_run_id

    with bind_run_id(run_id):
        if not settings.phoenix_enabled:
            yield
            return
        from openinference.instrumentation import using_metadata, using_session

        with using_session(run_id), using_metadata({"run_id": run_id}):
            yield


def flush_tracing() -> None:
    """Force-flush pending spans before process exit, so a short-lived CLI run
    doesn't lose spans still sitting in the exporter's buffer."""
    tracer_provider = _state.get("tracer_provider")
    if tracer_provider is not None and hasattr(tracer_provider, "force_flush"):
        tracer_provider.force_flush()


def is_initialized() -> bool:
    return _state["initialized"]


def get_client(base_url: str = PHOENIX_URL) -> Any:
    """Phoenix client for reading back spans."""
    from phoenix.client import Client

    return Client(base_url=base_url)


def reset_for_tests() -> None:
    """Test-only: allow re-initialization within the same process."""
    _state["initialized"] = False
    _state["tracer_provider"] = None
    _state["session"] = None
