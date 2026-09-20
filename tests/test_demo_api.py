"""Tests for scripts/demo_api.py (ref-doc.md §8.1 demonstrated local run).

Offline: the script's driver runs against the in-process app with a fake
graph through httpx's ASGI transport, so no server process starts and no
model is called.
"""

from __future__ import annotations

import json

import httpx
import pytest

import scripts.demo_api as demo
from src.api.app import create_app
from tests.test_api import _ANSWER, _REAL_PAN, FakeGraph, _finalize

_CONVS = [
    {"conversation_id": "conv-a", "customer_id": "C0001", "turns": ["What is my balance?"]},
    {"conversation_id": "conv-b", "customer_id": "C0001", "turns": ["First turn", "Second turn"]},
]


def _client(graph) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(graph)), base_url="http://test")


async def _run(graph, convs, tmp_path):
    log_path = tmp_path / "api_demo.log"
    log = demo.DemoLog(log_path)
    async with _client(graph) as client:
        ok = await demo.run_demo(client, convs, log)
    log.close()
    return ok, log_path.read_text(encoding="utf-8")


async def test_clean_run_succeeds_and_logs_every_stage(tmp_path):
    ok, text = await _run(FakeGraph([{"supervisor": {}}, _finalize()]), _CONVS, tmp_path)
    assert ok
    assert "GET /health -> 200" in text
    assert text.count("POST /chat/stream") == 3  # 1 + 2 turns
    assert "EVT  start" in text and "EVT  progress" in text and "EVT  final" in text
    assert "OK: 3 turn(s) over 2 conversation(s)" in text
    assert "Your balance is $100." in text


async def test_every_line_is_timestamped_and_carries_a_status(tmp_path):
    _, text = await _run(FakeGraph([_finalize()]), _CONVS[:1], tmp_path)
    for line in text.splitlines():
        ts, status, *_ = line.split()
        assert ts.endswith("+00:00") and status in {"INFO", "OK", "REQ", "EVT", "FAIL"}


async def test_a_leaked_pan_is_masked_in_the_log(tmp_path):
    leaked = {**_ANSWER, "answer": f"Your card is {_REAL_PAN}."}
    _, text = await _run(FakeGraph([_finalize(leaked)]), _CONVS[:1], tmp_path)
    assert _REAL_PAN not in text


async def test_an_error_frame_fails_the_run(tmp_path):
    graph = FakeGraph([], error=RuntimeError("boom"))
    ok, text = await _run(graph, _CONVS[:1], tmp_path)
    assert not ok
    assert "FAIL stream carried an error frame: internal_error" in text
    assert "FAILED: 1 turn(s)" in text


async def test_http_rejection_fails_the_run(tmp_path):
    bad = [{"conversation_id": "conv-x", "customer_id": "bad id!", "turns": ["hi"]}]
    ok, text = await _run(FakeGraph([_finalize()]), bad, tmp_path)
    assert not ok
    assert "HTTP 422" in text


async def test_unhealthy_server_fails_before_any_turn(tmp_path):
    app = create_app(None)
    app.state.graph = None  # not ready, but /health still answers 200 with graph_ready false
    log = demo.DemoLog(tmp_path / "l.log")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        ok = await demo.run_demo(client, _CONVS[:1], log)
    log.close()
    assert not ok  # /chat/stream answers 503


def test_parse_sse_groups_frames():
    lines = ['event: start', 'data: {"a": 1}', '', 'event: final', 'data: {"b": 2}', '']
    assert demo.parse_sse(lines) == [("start", {"a": 1}), ("final", {"b": 2})]


def test_check_frames_rules():
    start = ("start", {"disclosure": "AI"})
    assert demo._check_frames([start, ("final", {})]) is None
    assert "begin with a start" in demo._check_frames([("final", {})])
    assert "end with a final" in demo._check_frames([start, ("progress", {})])
    assert "no AI disclosure" in demo._check_frames([("start", {}), ("final", {})])


def test_load_conversations_keeps_order_and_rejects_unknown_ids(tmp_path):
    path = tmp_path / "c.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in _CONVS), encoding="utf-8")
    assert [c["conversation_id"] for c in demo.load_conversations(path, ["conv-b", "conv-a"])] == ["conv-b", "conv-a"]
    with pytest.raises(SystemExit):
        demo.load_conversations(path, ["conv-nope"])


def test_default_demo_conversations_exist_in_the_committed_samples():
    ids = demo.DEFAULT_CONVERSATIONS.split(",")
    assert [c["conversation_id"] for c in demo.load_conversations(demo.SAMPLE_INPUTS, ids)] == ids


async def test_events_are_logged_with_an_arrival_offset(tmp_path):
    import re

    _, text = await _run(FakeGraph([{"supervisor": {}}, _finalize()]), _CONVS[:1], tmp_path)
    evt_lines = [ln for ln in text.splitlines() if " EVT " in ln]
    assert evt_lines and all(re.search(r" EVT  \w+ \+\d+ms ", ln) for ln in evt_lines)
    assert "stream closed: 4 events" in text  # start, 2 progress, final
