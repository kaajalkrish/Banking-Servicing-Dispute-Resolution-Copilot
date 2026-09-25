"""Tests for the ingress sanitizer (D-10, AC-06, NFR-05)."""

from __future__ import annotations

import json
from pathlib import Path

from src.guardrails.ingress import sanitize_ingress

_ACCOUNTS = json.loads(Path("data/synthetic/accounts.json").read_text(encoding="utf-8"))
_REAL_PAN = _ACCOUNTS[0]["card_number"]


def test_pan_in_customer_text_is_masked():
    result = sanitize_ingress(f"My card number is {_REAL_PAN}, please help")
    assert result["had_pii"] is True
    assert _REAL_PAN not in result["sanitized_text"]
    assert any(d["entity_type"] == "CREDIT_CARD" for d in result["detections"])


def test_clean_text_is_returned_unchanged():
    text = "What is the overdraft fee on my account?"
    result = sanitize_ingress(text)
    assert result["had_pii"] is False
    assert result["sanitized_text"] == text
    assert result["detections"] == []
