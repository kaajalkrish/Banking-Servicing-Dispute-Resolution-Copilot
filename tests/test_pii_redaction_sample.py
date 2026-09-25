"""Tests for the PII redaction before/after sample generator (D-14, §8.1)."""

from __future__ import annotations

from scripts.pii_redaction_sample import SAMPLE_MESSAGES, build_samples


def test_every_sample_has_before_and_after():
    samples = build_samples()
    assert len(samples) == len(SAMPLE_MESSAGES)
    for s in samples:
        assert s["before"] and s["after"]


def test_pan_sample_is_redacted():
    samples = build_samples()
    pan_sample = next(s for s in samples if "4000009083863798" in s["before"])
    assert "4000009083863798" not in pan_sample["after"]
    assert pan_sample["had_pii"] is True


def test_clean_message_is_unchanged_and_flagged_no_pii():
    samples = build_samples()
    clean = next(s for s in samples if "overdraft fee" in s["before"])
    assert clean["before"] == clean["after"]
    assert clean["had_pii"] is False
    assert clean["detections"] == []
