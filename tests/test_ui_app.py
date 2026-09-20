"""Tests for the Streamlit UI (src/ui/app.py), driven by Streamlit's AppTest.

Offline: the client is replaced with a fake, so no API, model or network is used.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.common.disclosure import AI_DISCLOSURE
from src.ui import client

APP = str(Path(__file__).resolve().parents[1] / "src" / "ui" / "app.py")
_PAN = json.loads(Path("data/synthetic/accounts.json").read_text(encoding="utf-8"))[0]["card_number"]

_FINAL = {
    "answer": "Your balance is $100.",
    "citations": [],
    "requires_human_review": False,
    "risk_tier": "medium",
    "escalated": False,
}


def _events(final: dict | None = None, *, error: str | None = None) -> list[tuple[str, dict]]:
    events = [("start", {"disclosure": AI_DISCLOSURE}), ("progress", {"node": "supervisor"}), ("progress", {"node": "finalize"})]
    if error:
        events.append(("error", {"type": error}))
    events.append(("final", final or _FINAL))
    return events


@pytest.fixture
def app(monkeypatch):
    calls: list[tuple] = []

    def fake_stream(base_url, customer_id, message, thread_id, **_kw):
        calls.append((base_url, customer_id, message, thread_id))
        yield from _events()

    monkeypatch.setattr(client, "api_health", lambda *_a, **_k: {"status": "ok", "graph_ready": True})
    monkeypatch.setattr(client, "stream_chat", fake_stream)
    at = AppTest.from_file(APP, default_timeout=60)
    at.calls = calls
    return at.run()


def _markdown(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def _ask(at: AppTest, text: str = "What is my balance?") -> AppTest:
    return at.chat_input[0].set_value(text).run()


def test_first_render_shows_the_ai_disclosure_before_any_interaction(app):
    assert not app.exception
    assert [i.value for i in app.info] == [AI_DISCLOSURE]
    assert app.title[0].value == "Banking Servicing Copilot"
    assert len(app.chat_input) == 1
    assert len(app.chat_message) == 0


def test_sidebar_offers_the_synthetic_customers_and_reports_the_api_is_ready(app):
    # AppTest reports the formatted labels: "<customer id> (<synthetic name>)"
    assert [o.split(" ")[0] for o in app.sidebar.selectbox[0].options] == ["C0001", "C0002", "C0003", "C0004", "C0005"]
    assert [s.value for s in app.sidebar.success] == ["API ready"]


def test_an_unreachable_api_is_reported_with_the_command_to_start_it(monkeypatch):
    monkeypatch.setattr(client, "api_health", lambda *_a, **_k: None)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert "python -m src.api" in at.sidebar.error[0].value


def test_a_turn_shows_the_question_the_answer_and_its_risk_tier(app):
    at = _ask(app)
    assert not at.exception
    assert [m.name for m in at.chat_message] == ["user", "assistant"]
    assert "What is my balance?" in _markdown(at)
    assert "Your balance is $100." in _markdown(at)
    assert "Risk tier: medium" in [c.value for c in at.caption]
    assert len(at.warning) == 0


def test_the_turn_is_sent_for_the_selected_customer_with_a_ui_thread_id(app):
    _ask(app)
    base_url, customer_id, message, thread_id = app.calls[0]
    assert (base_url, customer_id, message) == (client.DEFAULT_API_URL, "C0001", "What is my balance?")
    assert thread_id.startswith("ui-")


def test_the_same_conversation_keeps_one_thread_across_turns(app):
    at = _ask(app, "first")
    _ask(at, "second")
    assert app.calls[0][3] == app.calls[1][3]


def test_a_high_risk_answer_is_flagged_for_human_review(monkeypatch, app):
    flagged = {**_FINAL, "risk_tier": "high", "requires_human_review": True, "escalated": True}
    monkeypatch.setattr(client, "stream_chat", lambda *a, **k: iter(_events(flagged)))
    at = _ask(app)
    assert any("human review" in w.value for w in at.warning)
    assert "Risk tier: high" in [c.value for c in at.caption]


def test_policy_sources_are_listed(monkeypatch, app):
    cited = {**_FINAL, "answer": "The overdraft fee is $35.", "citations": [{"doc_id": "POL-FEES", "section": "Overdraft Fee"}]}
    monkeypatch.setattr(client, "stream_chat", lambda *a, **k: iter(_events(cited)))
    at = _ask(app)
    assert "Sources: POL-FEES / Overdraft Fee" in [c.value for c in at.caption]


def test_a_card_number_in_an_answer_is_masked_before_display(monkeypatch, app):
    leaked = {**_FINAL, "answer": f"Your card is {_PAN}."}
    monkeypatch.setattr(client, "stream_chat", lambda *a, **k: iter(_events(leaked)))
    at = _ask(app)
    assert _PAN not in _markdown(at)


def test_an_error_frame_is_shown_as_a_warning_with_the_safe_answer(monkeypatch, app):
    safe = {**_FINAL, "answer": "This request needs a human banking agent.", "risk_tier": "high", "requires_human_review": True}
    monkeypatch.setattr(client, "stream_chat", lambda *a, **k: iter(_events(safe, error="timeout")))
    at = _ask(app)
    assert any("hit a problem (timeout)" in w.value for w in at.warning)
    assert "This request needs a human banking agent." in _markdown(at)


def test_an_api_failure_is_shown_as_an_error_not_a_crash(monkeypatch, app):
    def boom(*_a, **_k):
        raise client.ApiError("Cannot reach the copilot API at http://x. Start it with: python -m src.api")
        yield  # pragma: no cover  (makes this a generator like the real client)

    monkeypatch.setattr(client, "stream_chat", boom)
    at = _ask(app)
    assert not at.exception
    assert any("Cannot reach the copilot API" in e.value for e in at.error)


def test_new_conversation_clears_the_history_and_starts_a_new_thread(app):
    at = _ask(app)
    first_thread = app.calls[0][3]
    at = at.sidebar.button[0].click().run()
    assert len(at.chat_message) == 0
    _ask(at)
    assert app.calls[1][3] != first_thread


def test_switching_customer_starts_a_fresh_conversation(app):
    at = _ask(app)
    at = at.sidebar.selectbox[0].select("C0002").run()
    assert len(at.chat_message) == 0
    _ask(at)
    assert app.calls[-1][1] == "C0002"
