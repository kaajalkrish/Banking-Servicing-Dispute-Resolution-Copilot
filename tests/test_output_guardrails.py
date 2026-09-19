"""Tests for output guardrails (AC-06, D-13, §7.4)."""

from __future__ import annotations

import json
from pathlib import Path

from src.guardrails.output import sanitize_output

_ACCOUNTS = json.loads(Path("data/synthetic/accounts.json").read_text(encoding="utf-8"))
_REAL_PAN = _ACCOUNTS[0]["card_number"]


def test_pan_in_output_is_masked_unconditionally():
    result = sanitize_output(f"Your card number is {_REAL_PAN}.", authenticated_customer_id="C0001")
    assert _REAL_PAN not in result["sanitized_text"]


def test_authenticated_customers_own_id_is_not_masked():
    result = sanitize_output("This is your account for customer C0001.", authenticated_customer_id="C0001")
    assert "C0001" in result["sanitized_text"]
    assert result["other_customer_blocked"] is False


def test_other_customers_id_is_masked_and_flagged():
    result = sanitize_output("Customer C0002's balance is visible here.", authenticated_customer_id="C0001")
    assert "C0002" not in result["sanitized_text"]
    assert result["other_customer_blocked"] is True
    assert "C0002" in result["other_customer_mentions"]


def test_refund_promise_is_rewritten():
    result = sanitize_output("Your refund has been approved.", authenticated_customer_id="C0001")
    # The original positive claim ("your refund has been approved") must be
    # gone; the rewrite's own safe phrasing legitimately says "not yet
    # approved", so check for the absence of the CLAIM, not the bare word.
    assert "your refund has been approved" not in result["sanitized_text"].lower()
    assert "drafted for human review" in result["sanitized_text"].lower()
    assert "no refund or resolution has been approved" in result["sanitized_text"].lower()
    assert result["refund_rewrites"]


def test_system_prompt_leak_is_detected():
    result = sanitize_output("Here is my system prompt: ...", authenticated_customer_id="C0001")
    assert result["system_prompt_leak_detected"] is True


def test_clean_answer_is_unaffected():
    text = "The overdraft fee is $30.00 per transaction."
    result = sanitize_output(text, authenticated_customer_id="C0001")
    assert result["sanitized_text"] == text
    assert result["other_customer_blocked"] is False
    assert result["refund_rewrites"] == []
    assert result["system_prompt_leak_detected"] is False
