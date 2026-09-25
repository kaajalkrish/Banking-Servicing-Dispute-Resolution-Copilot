"""The chat CLI must tell the customer they are talking to an AI (docs/compliance.md)."""

from __future__ import annotations

from src.cli import chat_banner
from src.common.disclosure import AI_DISCLOSURE


def test_disclosure_says_ai_and_that_a_human_decides():
    text = AI_DISCLOSURE.lower()
    assert "ai assistant" in text
    assert "not a person" in text
    assert "human banking agent" in text


def test_interactive_banner_leads_with_disclosure_then_session_line():
    lines = chat_banner("C0001", "chat-C0001", interactive=True)
    assert lines[0] == AI_DISCLOSURE
    assert lines[1] == "Chat as C0001 (thread chat-C0001). Type 'exit' to quit."


def test_single_message_banner_still_discloses():
    assert chat_banner("C0001", "t", interactive=False) == [AI_DISCLOSURE]
