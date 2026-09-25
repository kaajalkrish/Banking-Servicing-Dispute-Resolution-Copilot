"""Tests for Presidio-based PII detection (AC-06, NFR-05, §8.1).

Uses real synthetic data (data/synthetic/accounts.json) rather than made-up
values, so the Luhn-valid PAN shape and our real account-number/customer-id
formats are genuinely exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.guardrails.pii import anonymize_text, detect_pii

_ACCOUNTS = json.loads(Path("data/synthetic/accounts.json").read_text(encoding="utf-8"))
_REAL_PAN = _ACCOUNTS[0]["card_number"]
_REAL_ACCOUNT_NUMBER = _ACCOUNTS[0]["account_number"]


def test_real_synthetic_pan_is_detected_as_credit_card():
    detections = detect_pii(f"My card is {_REAL_PAN}")
    assert any(d["entity_type"] == "CREDIT_CARD" for d in detections)


def test_real_synthetic_account_number_is_detected():
    detections = detect_pii(f"My account is {_REAL_ACCOUNT_NUMBER}")
    assert any(d["entity_type"] == "BANK_ACCOUNT_NUMBER" and d["score"] >= 0.9 for d in detections)


def test_customer_id_is_detected():
    detections = detect_pii("This is customer C0001's request")
    assert any(d["entity_type"] == "CUSTOMER_ID" for d in detections)


def test_anonymize_masks_all_three_shapes_with_no_leakage():
    text = f"My card number is {_REAL_PAN} and my account is {_REAL_ACCOUNT_NUMBER}, customer C0001."
    anonymized = anonymize_text(text)
    assert _REAL_PAN not in anonymized
    assert _REAL_ACCOUNT_NUMBER not in anonymized
    assert "C0001" not in anonymized
    assert "<CREDIT_CARD>" in anonymized
    assert "<BANK_ACCOUNT_NUMBER>" in anonymized
    assert "<CUSTOMER_ID>" in anonymized


def test_plain_text_with_no_pii_is_unchanged():
    text = "What is the overdraft fee on my account?"
    assert anonymize_text(text) == text
