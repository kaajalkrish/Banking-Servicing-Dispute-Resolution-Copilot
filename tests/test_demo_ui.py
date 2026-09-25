"""Tests for scripts/demo_ui.py (ref-doc.md §8.1 demonstrated local run).

Offline: src/ui/client.py's stream_chat/api_health are replaced with fakes
(the same pattern tests/test_ui_app.py uses), so no server process starts and
no model is called. run_ui_turn drives the REAL src/ui/app.py via Streamlit's
AppTest either way -- only the HTTP layer underneath is faked here.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import scripts.demo_ui as demo
from src.common.disclosure import AI_DISCLOSURE
from src.ui import client

_FINAL = {
    "answer": "Your balance is $100.",
    "citations": [],
    "requires_human_review": False,
    "risk_tier": "medium",
    "escalated": False,
}


def _events(final: dict | None = None) -> list[tuple[str, dict]]:
    return [
        ("start", {"disclosure": AI_DISCLOSURE}),
        ("progress", {"node": "supervisor"}),
        ("progress", {"node": "finalize"}),
        ("final", final or _FINAL),
    ]


@pytest.fixture(autouse=True)
def _healthy_api(monkeypatch):
    monkeypatch.setattr(client, "api_health", lambda *_a, **_k: {"status": "ok", "graph_ready": True})
    monkeypatch.setattr(client, "stream_chat", lambda *_a, **_k: iter(_events()))
    # run_ui_turn() sets these via plain os.environ[...] = ... (correct for a
    # real, one-shot script invocation), which otherwise leaks across tests
    # in the same pytest process and breaks unrelated tests that check these
    # exact env vars (found live: it broke test_ui_launcher.py, which expects
    # COPILOT_START_API to NOT be "0"). Snapshot and restore explicitly,
    # since monkeypatch only reverts changes made through monkeypatch itself.
    saved = {k: os.environ.get(k) for k in ("COPILOT_START_API", "COPILOT_API_URL")}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_clean_turn_succeeds_and_logs_the_real_answer(tmp_path):
    log = demo.DemoLog(tmp_path / "ui_demo.log")
    ok = demo.run_ui_turn("http://fake", "C0001", "What is my balance?", log)
    log.close()
    text = (tmp_path / "ui_demo.log").read_text(encoding="utf-8")
    assert ok
    assert "Your balance is $100." in text
    assert "OK   turn rendered" in text


def test_selecting_the_already_current_customer_does_not_attempt_a_reselect(tmp_path):
    # Regression test: .value is the raw option ("C0001"), .options are the
    # formatted display strings ("C0001 (name)") -- comparing .value against
    # a formatted string always differed, triggering a reselect that crashed
    # AppTest even when the requested customer was already selected (found
    # live running scripts/demo_ui.py for real).
    log = demo.DemoLog(tmp_path / "ui_demo.log")
    ok = demo.run_ui_turn("http://fake", "C0001", "What is my balance?", log)  # C0001 is the default
    log.close()
    assert ok  # would previously raise ValueError: None is not in list


def test_unreachable_api_fails_before_a_turn_is_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "api_health", lambda *_a, **_k: None)
    log = demo.DemoLog(tmp_path / "ui_demo.log")
    ok = demo.run_ui_turn("http://fake", "C0001", "What is my balance?", log)
    log.close()
    text = (tmp_path / "ui_demo.log").read_text(encoding="utf-8")
    assert not ok
    assert "FAIL" in text and "API as ready" in text


def test_a_stream_error_fails_the_run(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise client.ApiError("Cannot reach the copilot API")
        yield  # pragma: no cover  (makes this a generator like the real client)

    monkeypatch.setattr(client, "stream_chat", boom)
    log = demo.DemoLog(tmp_path / "ui_demo.log")
    ok = demo.run_ui_turn("http://fake", "C0001", "What is my balance?", log)
    log.close()
    text = (tmp_path / "ui_demo.log").read_text(encoding="utf-8")
    assert not ok
    assert "FAIL" in text and "error element rendered" in text


def test_a_leaked_pan_in_the_answer_is_masked_in_the_log(tmp_path, monkeypatch):
    import json

    pan = json.loads(Path("data/synthetic/accounts.json").read_text(encoding="utf-8"))[0]["card_number"]
    leaked = {**_FINAL, "answer": f"Your card is {pan}."}
    monkeypatch.setattr(client, "stream_chat", lambda *_a, **_k: iter(_events(leaked)))
    log = demo.DemoLog(tmp_path / "ui_demo.log")
    demo.run_ui_turn("http://fake", "C0001", "What is my card number?", log)
    log.close()
    text = (tmp_path / "ui_demo.log").read_text(encoding="utf-8")
    assert pan not in text


def test_unknown_customer_id_fails_cleanly(tmp_path):
    log = demo.DemoLog(tmp_path / "ui_demo.log")
    ok = demo.run_ui_turn("http://fake", "C9999", "hi", log)
    log.close()
    text = (tmp_path / "ui_demo.log").read_text(encoding="utf-8")
    assert not ok
    assert "not offered" in text


def test_demo_log_writes_timestamped_status_lines(tmp_path):
    path = tmp_path / "l.log"
    log = demo.DemoLog(path)
    log.line("OK", "hello")
    log.close()
    text = path.read_text(encoding="utf-8")
    assert "OK" in text and "hello" in text and "+00:00" in text
