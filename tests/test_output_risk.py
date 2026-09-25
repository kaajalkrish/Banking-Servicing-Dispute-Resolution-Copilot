"""Tests for output-risk classification (§7.5, AC-02, AC-04)."""

from __future__ import annotations

from src.guardrails.output_risk import classify_and_gate


def test_dispute_worker_is_always_high_risk_and_gated():
    result = classify_and_gate("dispute", "Your dispute has been drafted.", requires_human_review=True)
    assert result["risk_tier"] == "high"
    assert result["requires_human_review"] is True


def test_dispute_worker_forces_human_review_even_if_worker_forgot():
    """Backstop: a dispute answer is ALWAYS gated, even if requires_human_review
    was somehow False coming in (a future bug in dispute_node)."""
    result = classify_and_gate("dispute", "Your dispute has been drafted.", requires_human_review=False)
    assert result["risk_tier"] == "high"
    assert result["requires_human_review"] is True


def test_escalate_human_is_always_high_risk():
    result = classify_and_gate("escalate_human", "A human agent will follow up.", requires_human_review=True)
    assert result["risk_tier"] == "high"


def test_account_servicing_is_medium_risk():
    result = classify_and_gate("account_servicing", "Your balance is $100.", requires_human_review=False)
    assert result["risk_tier"] == "medium"
    assert result["requires_human_review"] is False


def test_product_info_confident_answer_is_low_risk():
    result = classify_and_gate("product_info", "The fee is $30 [POL-FEES].", requires_human_review=False)
    assert result["risk_tier"] == "low"


def test_product_info_abstention_stays_low_risk_despite_human_review_flag():
    """An honest abstention is not high-risk CONTENT even though it also sets
    requires_human_review=True for an unrelated reason (offering a human)."""
    result = classify_and_gate("product_info", "I don't have that information.", requires_human_review=True)
    assert result["risk_tier"] == "low"
    assert result["requires_human_review"] is True  # unrelated flag preserved as-is
