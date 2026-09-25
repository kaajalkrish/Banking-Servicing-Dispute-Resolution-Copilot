"""Consume the custom MCP server through langchain-mcp-adapters over stdio.

Builds a MultiServerMCPClient that launches ``python -m mcp_server.server`` as a
stdio subprocess, loads its tools as LangChain tools, and reads the
dispute-windows resource. All async (NFR-04). Verified against the installed
langchain-mcp-adapters API (get_tools / get_resources / session).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_NAME = "bank"
DISPUTE_WINDOWS_URI = "bank://reference/dispute-windows"


def _subprocess_env() -> dict[str, str]:
    """Environment for the stdio subprocess: inherit parent, ensure importable."""
    env = dict(os.environ)
    # Make the repo importable from the child regardless of its cwd.
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(_REPO_ROOT), existing) if p)
    env.setdefault("LOG_DIR", str(_REPO_ROOT / "logs"))
    return env


def build_connections() -> dict[str, dict[str, Any]]:
    """Stdio connection config for the bank MCP server."""
    return {
        SERVER_NAME: {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "mcp_server.server"],
            "cwd": str(_REPO_ROOT),
            "env": _subprocess_env(),
        }
    }


def get_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(build_connections())


async def get_mcp_tools(client: MultiServerMCPClient | None = None) -> list[BaseTool]:
    """Load the MCP server's tools as LangChain tools."""
    client = client or get_client()
    return await client.get_tools(server_name=SERVER_NAME)


async def get_dispute_windows(client: MultiServerMCPClient | None = None) -> str:
    """Read the dispute-windows reference resource (returns its text payload)."""
    client = client or get_client()
    blobs = await client.get_resources(SERVER_NAME, uris=DISPUTE_WINDOWS_URI)
    if not blobs:
        return ""
    blob = blobs[0]
    data = getattr(blob, "data", b"")
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


if __name__ == "__main__":
    import asyncio

    async def _main() -> None:
        tools = await get_mcp_tools()
        # stderr, never stdout (mustn't interfere if piped)
        print("MCP tools:", sorted(t.name for t in tools), file=sys.stderr)
        print("dispute-windows:", (await get_dispute_windows())[:80], file=sys.stderr)

    asyncio.run(_main())
