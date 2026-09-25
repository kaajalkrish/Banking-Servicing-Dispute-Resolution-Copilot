"""Tests for the tool-name reconciliation script (AC-07)."""

from __future__ import annotations

import json

import pytest

import scripts.verify_tool_names as v


async def test_defined_mcp_tool_names_matches_server():
    defined = await v._defined_mcp_tool_names()
    assert "get_account_balance" in defined
    assert "check_dispute_eligibility" in defined
    assert len(defined) == 7  # matches mcp_server/server.py's registered tool count


def test_logged_names_read_both_log_files(tmp_path):
    (tmp_path / "tool_calls.jsonl").write_text(
        json.dumps({"tool_name": "get_account_balance"}) + "\n", encoding="utf-8"
    )
    (tmp_path / "mcp_transcript.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"method": "tools/call", "name": "create_dispute_case"}),
                json.dumps({"method": "resources/read", "name": "bank://reference/dispute-windows"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names = v._logged_tool_call_names(tmp_path)
    assert names == {"get_account_balance", "create_dispute_case"}  # resource read excluded


def test_missing_log_files_return_empty_set(tmp_path):
    assert v._logged_tool_call_names(tmp_path) == set()


async def test_unknown_tool_name_is_flagged():
    defined = await v._defined_mcp_tool_names() | v.LOCAL_TOOL_NAMES
    logged = {"get_account_balance", "a_tool_that_does_not_exist"}
    unknown = logged - defined
    assert unknown == {"a_tool_that_does_not_exist"}
