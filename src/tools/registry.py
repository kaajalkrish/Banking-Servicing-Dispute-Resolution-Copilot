"""Single place every tool is wrapped and logged (P3-07, AC-07).

``build_tools(agent_name, raw_tools)`` wraps each raw tool with the resilience
wrapper (timeout/retry -> structured failure) and then the logging middleware
(so a timeout/retry-exhausted failure is still logged with ``status="error"``),
so a worker just calls ``tool.ainvoke(args)`` directly and gets both
resilience and logging for free. Workers no longer call
``resilient_ainvoke()`` themselves — no tool call can bypass the log by going
around this registry.
"""

from __future__ import annotations

from typing import Any

from src.observability.tool_logging import LoggedTool
from src.tools.resilience import ResilientTool


def build_tools(agent_name: str, raw_tools: list[Any]) -> list[Any]:
    """Wrap every tool in ``raw_tools`` with resilience + logging, tagged with
    ``agent_name`` for the tool-invocation log's ``agent`` field."""
    return [LoggedTool(ResilientTool(t), agent=agent_name) for t in raw_tools]
