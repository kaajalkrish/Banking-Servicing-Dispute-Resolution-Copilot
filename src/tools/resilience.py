"""Resilient async tool invocation (NFR-04, §7.1).

Wraps a tool call in a timeout with bounded retries and returns a structured
ToolFailure instead of raising, so workers degrade gracefully (apologise /
escalate) rather than crash. Retries apply to timeouts and transient errors;
other errors fail fast after being captured as a structured failure.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from src.config import settings
from src.llm import _is_transient


def tool_failure(tool_name: str, exc: Exception | str, kind: str = "error") -> dict[str, Any]:
    """Structured failure object (never raised)."""
    message = exc if isinstance(exc, str) else str(exc)
    return {
        "ok": False,
        "tool": tool_name,
        "error": {"type": kind, "message": message},
    }


async def resilient_ainvoke(
    tool: Any,
    tool_input: dict[str, Any],
    *,
    tool_name: str | None = None,
    timeout: float | None = None,
    retries: int | None = None,
) -> Any:
    """Invoke ``tool.ainvoke(tool_input)`` with timeout + retry.

    Returns the tool result on success, or a ToolFailure dict on timeout /
    transient exhaustion / error. Never raises to the caller.
    """
    name = tool_name or getattr(tool, "name", getattr(tool, "__name__", "tool"))
    timeout = settings.request_timeout_s if timeout is None else timeout
    retries = settings.max_retries if retries is None else retries

    attempt = 0
    while True:
        try:
            return await asyncio.wait_for(tool.ainvoke(tool_input), timeout=timeout)
        except asyncio.TimeoutError:
            if attempt >= retries:
                return tool_failure(name, f"timed out after {timeout}s", kind="TimeoutError")
        except Exception as exc:  # noqa: BLE001
            if not _is_transient(exc) or attempt >= retries:
                return tool_failure(name, exc, kind=type(exc).__name__)
        delay = min(10.0, 0.5 * (2 ** attempt)) * (0.5 + random.random())
        attempt += 1
        await asyncio.sleep(delay)


class ResilientTool:
    """Wraps a tool so every ``.ainvoke()`` call automatically goes through
    resilient_ainvoke (P3-07 registry composes this with LoggedTool so a
    timeout/retry-exhausted failure still gets logged with status='error')."""

    def __init__(self, tool: Any, *, timeout: float | None = None, retries: int | None = None) -> None:
        self._tool = tool
        self.name = getattr(tool, "name", getattr(tool, "__name__", "tool"))
        self._timeout = timeout
        self._retries = retries

    async def ainvoke(self, tool_input: dict[str, Any]) -> Any:
        return await resilient_ainvoke(
            self._tool, tool_input, tool_name=self.name, timeout=self._timeout, retries=self._retries
        )
