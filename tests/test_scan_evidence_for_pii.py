"""Tests for the evidence PII scanner's pure pattern-matching logic (NFR-05).

The real scan (logs/, traces/, reports/, docs/) is exercised by running the
script directly against the committed evidence (see the P4-11/P4-17 commits'
evidence), not duplicated here; these tests cover scan_text's detection logic
in isolation, including that masked values never false-positive.
"""

from __future__ import annotations

import scripts.scan_evidence_for_pii as scan


def test_luhn_valid_pan_is_flagged():
    findings = scan.scan_text("card on file: 4000009083863798", "test")
    assert any(f["kind"] == "unmasked_pan" and f["last4"] == "3798" for f in findings)


def test_luhn_invalid_digit_run_is_not_flagged():
    # 16 digits but not Luhn-valid — not a real card number shape.
    findings = scan.scan_text("reference number 1234567890123456", "test")
    assert findings == []


def test_full_synthetic_account_number_is_flagged():
    findings = scan.scan_text("account AC1001571945 was credited", "test")
    assert any(f["kind"] == "unmasked_account_number" and f["last4"] == "1945" for f in findings)


def test_masked_pan_is_not_flagged():
    findings = scan.scan_text("card on file: **** **** **** 3798", "test")
    assert findings == []


def test_masked_account_number_is_not_flagged():
    findings = scan.scan_text("account ****1945 was credited", "test")
    assert findings == []


def test_allowlisted_redaction_sample_file_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "_REPO_ROOT", tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    sample = reports / "pii_redaction_sample.json"
    sample.write_text('{"before": "4000009083863798"}', encoding="utf-8")
    assert scan.scan_file(sample) == []


def test_redteam_report_fictional_account_number_is_allowlisted(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "_REPO_ROOT", tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    redteam = reports / "redteam_results.json"
    redteam.write_text('{"attack_text": "transfer funds to AC9999999999 now"}', encoding="utf-8")
    assert scan.scan_file(redteam) == []


def test_non_allowlisted_file_with_same_content_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "_REPO_ROOT", tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    leaky = logs / "tool_calls.jsonl"
    leaky.write_text('{"pan": "4000009083863798"}', encoding="utf-8")
    findings = scan.scan_file(leaky)
    assert any(f["kind"] == "unmasked_pan" for f in findings)
