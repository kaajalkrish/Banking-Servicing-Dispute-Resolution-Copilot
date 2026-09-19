"""Tests for the tool registry (P3-07): every tool routed through resilience
+ logging, no bypass possible.
"""

from __future__ import annotations

import asyncio
import json

from src.common.ids import bind_run_id
from src.tools.registry import build_tools


class _OkTool:
    name = "get_account_balance"

    async def ainvoke(self, args):
        return {"balance": 100}


class _RaisingTool:
    name = "boom"

    async def ainvoke(self, args):
        raise RuntimeError("kaboom")


async def test_build_tools_wraps_with_resilience_and_logging(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    tools = build_tools("account_servicing", [_OkTool(), _RaisingTool()])
    assert [t.name for t in tools] == ["get_account_balance", "boom"]

    with bind_run_id("run-registry-test"):
        ok_result = await tools[0].ainvoke({"customer_id": "C0001"})
        assert ok_result == {"balance": 100}

        # a raised exception in the wrapped tool never propagates -- the
        # resilience layer converts it to a structured failure.
        fail_result = await tools[1].ainvoke({})
        assert fail_result["ok"] is False
        assert fail_result["error"]["type"] == "RuntimeError"

    records = [json.loads(line) for line in (tmp_path / "tool_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert records[0]["agent"] == "account_servicing" and records[0]["status"] == "ok"
    assert records[1]["agent"] == "account_servicing" and records[1]["status"] == "error"
    assert all(r["run_id"] == "run-registry-test" for r in records)


async def test_different_agents_produce_differently_tagged_wrappers(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    raw = _OkTool()
    account_tools = build_tools("account_servicing", [raw])
    dispute_tools = build_tools("dispute", [raw])

    with bind_run_id("run-tag-test"):
        await account_tools[0].ainvoke({})
        await dispute_tools[0].ainvoke({})

    records = [json.loads(line) for line in (tmp_path / "tool_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["agent"] for r in records] == ["account_servicing", "dispute"]
