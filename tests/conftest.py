"""Shared pytest fixtures.

Keeps the default test run offline and side-effect-free: every test writes logs
to a temp directory instead of the committed logs/ tree.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _tmp_log_dir(tmp_path, monkeypatch):
    """Redirect LOG_DIR to a per-test temp dir so tests never touch real logs/."""
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))


@pytest.fixture(scope="session")
def tool_input_schemas() -> dict[str, dict]:
    """Registered MCP tool name -> JSON input schema (from the server)."""
    from mcp_server.server import mcp

    tools = asyncio.run(mcp.list_tools())
    return {t.name: t.inputSchema for t in tools}
