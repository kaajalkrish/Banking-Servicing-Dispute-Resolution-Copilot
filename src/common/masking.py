"""PAN / account-number / PII masking utilities (NFR-05, AC-06, §3.4).

Every log, trace and structured output must route sensitive values through
these helpers so that account and card numbers are never written in plaintext.
Masking keeps only the last four digits so records stay useful for support
without exposing the full number.

Deterministic, standard-library only, no network.
"""

from __future__ import annotations

import re
from typing import Any

# 13–19 digit runs, optionally split by spaces or hyphens (card/account shapes).
_DIGIT_RUN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

# Field names whose values are always treated as sensitive regardless of content.
_SENSITIVE_KEYS = {
    "pan",
    "card_number",
    "cardnumber",
    "card",
    "account_number",
    "accountnumber",
    "account",
    "acct",
    "acct_number",
}


def luhn_check(number: str) -> bool:
    """Return True if the digit string passes the Luhn checksum."""
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 12:
        return False
    total = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _last4(digits: str) -> str:
    d = re.sub(r"\D", "", digits)
    return d[-4:] if len(d) >= 4 else d


def mask_pan(pan: str) -> str:
    """Mask a card number to its last four digits: ``**** **** **** 1234``."""
    return f"**** **** **** {_last4(pan)}"


def mask_account(account: str) -> str:
    """Mask an account number to its last four digits: ``****1234``."""
    return f"****{_last4(account)}"


def _mask_digit_run(match: re.Match[str]) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    # Only mask sequences that look like real card/account numbers. A Luhn-valid
    # 13–19 digit run is treated as a PAN; other long runs are masked too, since
    # the rule is "never write account numbers in plaintext".
    if luhn_check(digits):
        return mask_pan(digits)
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


def mask_text(text: str) -> str:
    """Mask any card/account-like digit runs embedded in free text."""
    return _DIGIT_RUN.sub(_mask_digit_run, text)


def mask_obj(obj: Any) -> Any:
    """Recursively mask a value for safe logging.

    - dict: sensitive keys have their values fully masked; other string values
      are scanned for embedded card/account numbers.
    - list/tuple: each element is masked.
    - str: embedded digit runs are masked.
    - other scalars: returned unchanged.
    """
    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS and isinstance(v, str):
                out[k] = mask_pan(v) if luhn_check(v) else mask_account(v)
            else:
                out[k] = mask_obj(v)
        return out
    if isinstance(obj, (list, tuple)):
        return type(obj)(mask_obj(v) for v in obj)
    if isinstance(obj, str):
        return mask_text(obj)
    return obj
