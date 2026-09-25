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


# ---- hex identifiers must not be mistaken for card numbers ----------------

_LUHN_13 = "4222222222222"  # a Luhn-valid 13-digit number (classic test PAN)


def _raw_luhn_hits(text: str) -> int:
    """Digit runs a naive scanner would flag (guards each test's premise)."""
    return sum(
        1
        for m in scan._DIGIT_RUN.finditer(text)
        if scan.luhn_check(scan.re.sub(r"\D", "", m.group(0)))
    )


def _has_hex_letter(text: str) -> bool:
    return any(c in "abcdefABCDEF" for c in text)


def test_luhn_valid_run_inside_a_32_hex_id_is_not_flagged():
    trace_id = "ea6e" + _LUHN_13 + "a275de744b5ceee"  # 4 + 13 + 15 = 32 hex chars
    text = f'{{"id": "{trace_id}"}}'
    assert _raw_luhn_hits(text) >= 1
    assert scan.scan_text(text, "x") == []


def test_luhn_valid_run_inside_a_16_hex_span_id_is_not_flagged():
    span_id = "ab" + _LUHN_13 + "c"  # 2 + 13 + 1 = 16 hex chars
    assert _raw_luhn_hits(span_id) >= 1
    assert scan.scan_text(f"span_id={span_id}", "x") == []


def test_luhn_valid_run_inside_a_uuid_is_not_flagged():
    import random
    import uuid

    rng = random.Random(7)
    for _ in range(200000):
        candidate = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        if _raw_luhn_hits(candidate) and _has_hex_letter(candidate):
            break
    else:
        raise AssertionError("no Luhn-bearing UUID found by the seeded search")
    assert scan.scan_text(f"run-{candidate}", "x") == []


def test_real_pan_next_to_a_hex_id_is_still_flagged():
    text = f"id ea6e{_LUHN_13}a275de744b5ceee card {_LUHN_13}"
    found = scan.scan_text(text, "x")
    assert [f["last4"] for f in found] == [_LUHN_13[-4:]]


def test_pan_glued_to_letters_is_still_flagged():
    assert [f["kind"] for f in scan.scan_text(f"card{_LUHN_13}", "x")] == ["unmasked_pan"]


def test_a_16_digit_number_is_never_treated_as_an_identifier():
    pan16 = "4111111111111111"  # Luhn-valid, all digits: no a-f letter, so not an id
    assert [f["kind"] for f in scan.scan_text(f"pan={pan16}", "x")] == ["unmasked_pan"]


def _luhn_completed(prefix: str) -> str:
    """``prefix`` plus the check digit that makes it Luhn-valid."""
    return next(prefix + str(d) for d in range(10) if scan.luhn_check(prefix + str(d)))


def test_a_float_fraction_is_not_flagged_as_a_card_number():
    fraction = _luhn_completed("1234567890123456")  # 17 digits, Luhn-valid
    text = f'{{"distance": 0.{fraction}}}'
    assert _raw_luhn_hits(text) >= 1
    assert scan.scan_text(text, "x") == []


def test_a_pan_after_a_full_stop_and_letter_is_still_flagged():
    assert [f["kind"] for f in scan.scan_text(f"Thanks.{_LUHN_13}", "x")] == ["unmasked_pan"]


def test_a_langchain_run_id_with_a_trailing_suffix_is_not_flagged():
    # lc_run--<uuid>-0: the digit-run pattern absorbs the trailing "-0", so the
    # run starts inside the UUID but ends after it.
    tail = next(
        f"{n:012d}"
        for n in range(10**6)
        if scan.luhn_check(f"{n:012d}0")
    )
    text = f'"id": "lc_run--01a0bb8c-947b-7ae0-813e-{tail}-0"'
    assert _raw_luhn_hits(text) >= 1
    assert scan.scan_text(text, "x") == []
