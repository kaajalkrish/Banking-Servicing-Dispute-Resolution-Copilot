"""Tests for the secrets scanner's pure pattern-matching logic (NFR-01).

The real scan (working tree + git history) is exercised by running the script
directly (see the P4-10 commit's evidence), not duplicated here; these tests
cover the detection patterns and env-hygiene logic in isolation.
"""

from __future__ import annotations

import scripts.check_secrets as cs


def test_google_api_key_pattern_matches():
    text = "GOOGLE_API_KEY=AIzaSyD1234567890abcdefghijklmnopqrstuv"
    findings = cs.scan_text(text, "test")
    assert any(f["pattern"] == "google_api_key" for f in findings)


def test_oauth_token_pattern_matches():
    text = "token=ya29.a0AfH6SMBexampletokenvalue1234567890"
    findings = cs.scan_text(text, "test")
    assert any(f["pattern"] == "google_oauth_token" for f in findings)


def test_private_key_block_matches():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIExampleKeyContent\n-----END RSA PRIVATE KEY-----"
    findings = cs.scan_text(text, "test")
    assert any(f["pattern"] == "private_key_block" for f in findings)


def test_plain_config_text_has_no_findings():
    text = "GEMINI_MODEL=gemini-3.5-flash\nLOG_DIR=logs\nMAX_STEPS=12"
    assert cs.scan_text(text, "test") == []


def test_match_prefix_never_includes_the_full_secret():
    text = "AIzaSyD1234567890abcdefghijklmnopqrstuv"
    findings = cs.scan_text(text, "test")
    assert len(findings) == 1
    assert len(findings[0]["match_prefix"]) < len(text)
    assert "1234567890abcdefghijklmnopqrstuv" not in findings[0]["match_prefix"]


def test_own_test_fixture_file_is_excluded_from_the_real_scan():
    # This test file itself contains fake secret-shaped literals (above) to
    # exercise scan_text's pattern matching -- a real end-to-end run must not
    # flag its own fixtures as findings (found by actually running the
    # scanner, not assumed).
    tree_findings = cs.scan_working_tree()
    assert not any("test_check_secrets.py" in f["source"] for f in tree_findings)
