"""Reconcile tool names in the logs against the tools actually defined in code.

Compares the distinct tool_name values found in logs/tool_calls.jsonl and the
tools/call entries of logs/mcp_transcript.jsonl against the real registered
tool set (MCP server introspection + local tools like policy_search).
Writes reports/tool_reconciliation.json. Exits non-zero if a logged name does
not correspond to any defined tool (AC-07: "names reconcile with agent/MCP
code") -- a defined tool that was simply never exercised in this run is
reported but does not fail the check.

Usage:
    python scripts/verify_tool_names.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

LOCAL_TOOL_NAMES = {"policy_search"}  # tools not served by the MCP server


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _defined_mcp_tool_names() -> set[str]:
    from mcp_server.server import mcp

    tools = await mcp.list_tools()
    return {t.name for t in tools}


def _logged_tool_call_names(log_dir: Path) -> set[str]:
    names: set[str] = set()
    for entry in _read_jsonl(log_dir / "tool_calls.jsonl"):
        if "tool_name" in entry:
            names.add(entry["tool_name"])
    for entry in _read_jsonl(log_dir / "mcp_transcript.jsonl"):
        if entry.get("method") == "tools/call" and "name" in entry:
            names.add(entry["name"])
    return names


def main() -> int:
    log_dir = _REPO_ROOT / "logs"
    reports_dir = _REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    defined = asyncio.run(_defined_mcp_tool_names()) | LOCAL_TOOL_NAMES
    logged = _logged_tool_call_names(log_dir)

    unknown_in_logs = sorted(logged - defined)  # a real problem
    never_exercised = sorted(defined - logged)  # informational only

    result = {
        "defined_tools": sorted(defined),
        "logged_tools": sorted(logged),
        "unknown_in_logs": unknown_in_logs,
        "never_exercised": never_exercised,
        "ok": not unknown_in_logs,
    }
    (reports_dir / "tool_reconciliation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"defined tools: {len(defined)} | logged tools: {len(logged)}")
    if unknown_in_logs:
        print(f"FAIL: tool name(s) in logs with no matching definition: {unknown_in_logs}")
        return 1
    if never_exercised:
        print(f"note: defined but not yet exercised in these logs: {never_exercised}")
    print("OK: every logged tool name reconciles with a defined tool.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
