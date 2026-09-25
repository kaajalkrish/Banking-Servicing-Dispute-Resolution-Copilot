"""Tests for the tool-invocation logging middleware (AC-07, §7.2)."""

from __future__ import annotations

import json
import os

from src.common.ids import bind_run_id
from src.observability.tool_logging import LoggedTool

REQUIRED_FIELDS = {"timestamp", "run_id", "agent", "tool_name", "args", "result", "latency_ms", "status"}


class _OkTool:
    name = "get_account_balance"

    async def ainvoke(self, args):
        return {"balance": 100, "card_number": "4111111111111111"}


class _StructuredErrorTool:
    name = "create_dispute_case"

    async def ainvoke(self, args):
        return {"error": {"type": "LookupError", "message": "not found"}}


class _RaisingTool:
    name = "boom"

    async def ainvoke(self, args):
        raise RuntimeError("kaboom")


def _read_records(log_dir) -> list[dict]:
    path = log_dir / "tool_calls.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_successful_call_is_logged_with_all_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    with bind_run_id("run-abc123"):
        result = await LoggedTool(_OkTool(), agent="account_servicing").ainvoke({"customer_id": "C0001"})
    assert result["balance"] == 100

    records = _read_records(tmp_path)
    assert len(records) == 1
    assert REQUIRED_FIELDS <= set(records[0])
    assert records[0]["status"] == "ok"
    assert records[0]["run_id"] == "run-abc123"
    assert records[0]["agent"] == "account_servicing"
    assert records[0]["tool_name"] == "get_account_balance"


async def test_structured_error_result_is_logged_as_error(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    result = await LoggedTool(_StructuredErrorTool(), agent="dispute").ainvoke({})
    assert "error" in result
    records = _read_records(tmp_path)
    assert records[0]["status"] == "error"


async def test_raised_exception_is_logged_then_reraised(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="kaboom"):
        await LoggedTool(_RaisingTool(), agent="dispute").ainvoke({})
    records = _read_records(tmp_path)
    assert records[0]["status"] == "error"
    assert "kaboom" in records[0]["result"]["error"]["message"]


async def test_run_id_is_none_outside_bind_run_id_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    await LoggedTool(_OkTool(), agent="account_servicing").ainvoke({"customer_id": "C0001"})
    records = _read_records(tmp_path)
    assert records[0]["run_id"] is None


async def test_pan_never_appears_in_plaintext(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    await LoggedTool(_OkTool(), agent="account_servicing").ainvoke({"customer_id": "C0001"})
    blob = (tmp_path / "tool_calls.jsonl").read_text(encoding="utf-8")
    assert "4111111111111111" not in blob
