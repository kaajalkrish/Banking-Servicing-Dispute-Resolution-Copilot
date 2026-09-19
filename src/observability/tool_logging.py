"""Tool-invocation logging middleware (AC-07, §7.2 Tool-invocation log).

Wraps a tool-shaped object (``.name`` + async ``.ainvoke(dict)``) so every call
appends one masked JSON record to ``logs/tool_calls.jsonl``: timestamp,
run_id, agent, tool_name, args, result, latency_ms, status. Atomic append
(single ``write()`` call under a lock), async-safe. The run_id comes from
``src.common.ids.get_current_run_id()`` — set by ``traced_run()`` — and is
present even when Phoenix tracing itself is disabled.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.ids import get_current_run_id
from src.common.masking import mask_obj

_write_lock = threading.Lock()


def _path() -> Path:
    d = Path(os.environ.get("LOG_DIR", "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "tool_calls.jsonl"


def _append(record: dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _write_lock:
        with _path().open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()


class LoggedTool:
    """Logging wrapper around a tool. Delegates ``.name`` from the wrapped
    tool so it still looks like a tool to callers (e.g. ``get_tool()``'s
    ``getattr(t, "name", None)`` matching)."""

    def __init__(self, tool: Any, *, agent: str) -> None:
        self._tool = tool
        self._agent = agent
        self.name = getattr(tool, "name", getattr(tool, "__name__", "tool"))

    async def ainvoke(self, args: dict[str, Any]) -> Any:
        start = time.perf_counter()
        status = "ok"
        result: Any = None
        try:
            result = await self._tool.ainvoke(args)
            # A structured failure from resilient_ainvoke, or an MCP tool's
            # own {"error": {...}} shape, both count as a logged error status.
            if isinstance(result, dict) and ("error" in result or result.get("ok") is False):
                status = "error"
            return result
        except Exception as exc:  # noqa: BLE001 - always log, then re-raise
            status = "error"
            result = {"error": {"type": type(exc).__name__, "message": str(exc)}}
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            _append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "run_id": get_current_run_id(),
                    "agent": self._agent,
                    "tool_name": self.name,
                    "args": mask_obj(args),
                    "result": mask_obj(result),
                    "latency_ms": round(latency_ms, 2),
                    "status": status,
                }
            )
