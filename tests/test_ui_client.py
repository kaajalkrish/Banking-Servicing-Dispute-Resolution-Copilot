"""Tests for the Streamlit UI's HTTP client (src/ui/client.py).

Offline: the client is exercised against the real FastAPI app with a fake graph
(a FastAPI ``TestClient`` is an ``httpx.Client``), so the SSE protocol between
the API and the UI is tested end to end without a model or a network.
"""

from __future__ import annotations

import re

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.common.disclosure import AI_DISCLOSURE
from src.ui import client
from tests.test_api import FakeGraph, _finalize


def _events(graph: FakeGraph, **kw):
    http = TestClient(create_app(graph))
    return list(client.stream_chat("http://testserver", "C0001", "What is my balance?", "t1", http_client=http, **kw))


def test_iter_sse_yields_each_event_as_its_blank_line_arrives():
    lines = ["event: start", 'data: {"a": 1}', "", ": comment", "event: final", 'data: {"b": 2}', ""]
    assert list(client.iter_sse(lines)) == [("start", {"a": 1}), ("final", {"b": 2})]


def test_iter_sse_is_lazy_so_progress_can_be_shown_mid_turn():
    seen = []

    def lines():
        yield "event: progress"
        yield 'data: {"node": "supervisor"}'
        yield ""
        seen.append("after-first-frame")  # not reached until the consumer asks for more
        yield "event: final"
        yield 'data: {"answer": "x"}'
        yield ""

    it = client.iter_sse(lines())
    assert next(it) == ("progress", {"node": "supervisor"})
    assert seen == []


def test_stream_chat_yields_start_progress_and_final_with_the_disclosure():
    events = _events(FakeGraph([{"supervisor": {}}, _finalize()]))
    assert [e for e, _ in events] == ["start", "progress", "progress", "final"]
    assert events[0][1]["disclosure"] == AI_DISCLOSURE
    assert events[-1][1]["answer"] == "Your balance is $100."


def test_stream_chat_sends_the_customer_message_and_a_namespaced_thread():
    graph = FakeGraph([_finalize()])
    _events(graph)
    state, config, _ = graph.calls[0]
    assert state["customer_id"] == "C0001"
    assert config["configurable"]["thread_id"] == "C0001:t1"


def test_an_error_frame_from_the_api_reaches_the_ui_with_a_safe_final():
    events = _events(FakeGraph([], error=RuntimeError("secret detail")))
    names = [e for e, _ in events]
    assert names == ["start", "error", "final"]
    assert "secret detail" not in str(events)


def test_a_rejected_request_raises_a_readable_error():
    http = TestClient(create_app(FakeGraph([_finalize()])))
    with pytest.raises(client.ApiError, match="not accepted"):
        list(client.stream_chat("http://testserver", "bad id!", "hi", "t1", http_client=http))


def test_an_api_that_is_not_ready_raises_a_readable_error():
    app = create_app(None)
    app.state.graph = None
    with pytest.raises(client.ApiError, match="not ready"):
        list(client.stream_chat("http://testserver", "C0001", "hi", "t1", http_client=TestClient(app)))


def _failing_client(exc: Exception) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler))


def test_an_unreachable_api_tells_the_user_how_to_start_it():
    with pytest.raises(client.ApiError, match=r"python -m src\.api"):
        list(client.stream_chat("http://x", "C0001", "hi", "t1", http_client=_failing_client(httpx.ConnectError("no"))))


def test_a_timeout_raises_a_readable_error():
    with pytest.raises(client.ApiError, match="too long"):
        list(client.stream_chat("http://x", "C0001", "hi", "t1", http_client=_failing_client(httpx.ReadTimeout("slow"))))


def test_api_health_returns_the_payload_or_none():
    assert client.api_health("http://testserver", http_client=TestClient(create_app(FakeGraph([])))) == {
        "status": "ok",
        "graph_ready": True,
    }
    assert client.api_health("http://x", http_client=_failing_client(httpx.ConnectError("no"))) is None
    assert client.api_health("http://127.0.0.1:9", timeout=0.5) is None  # nothing listens on port 9


def test_customers_come_from_the_synthetic_data():
    customers = client.load_customers()
    assert [cid for cid, _ in customers] == ["C0001", "C0002", "C0003", "C0004", "C0005"]
    assert all(name for _, name in customers)


def test_a_new_thread_id_is_accepted_by_the_api_pattern_and_unique():
    ids = {client.new_thread_id() for _ in range(20)}
    assert len(ids) == 20
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", i) for i in ids)
