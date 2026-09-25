"""Input guardrails: injection, cross-customer references, length limits
(AC-06, NFR-03, §7.4). Combines injection.py's pattern detection with a
cross-customer-reference check (reusing pii.py's CUSTOMER_ID recognizer) into
one allow/sanitize/block decision with a reason code, ready for the audit
trail and for wiring into the graph's I/O path (P4-09).
"""

from __future__ import annotations

from typing import Any, Literal

from src.guardrails.injection import detect_injection
from src.guardrails.pii import detect_pii

Decision = Literal["allow", "sanitize", "block"]

MAX_INPUT_LENGTH = 4000


def detect_cross_customer_reference(text: str, authenticated_customer_id: str) -> list[str]:
    """Return any CUSTOMER_ID-shaped mention in `text` that is NOT the
    authenticated customer — a request that names a different customer."""
    detections = detect_pii(text or "")
    mentions = []
    for d in detections:
        if d["entity_type"] == "CUSTOMER_ID":
            mention = text[d["start"] : d["end"]]
            if mention != authenticated_customer_id:
                mentions.append(mention)
    return mentions


def evaluate_input(text: str, *, authenticated_customer_id: str) -> dict[str, Any]:
    """Evaluate raw (already ingress-sanitized) customer text.

    Checked in order of severity: length, then injection, then cross-customer
    reference — the first violation found decides the outcome, since these
    are all "block" cases (there's no legitimate "sanitize" here — a mixed
    injection+legitimate message is still an injection attempt).
    """
    text = text or ""

    if len(text) > MAX_INPUT_LENGTH:
        return {"decision": "block", "reason_code": "input_too_long", "details": {"length": len(text)}}

    injection_hits = detect_injection(text)
    if injection_hits:
        return {
            "decision": "block",
            "reason_code": "prompt_injection_detected",
            "details": {"patterns": injection_hits},
        }

    cross_customer_hits = detect_cross_customer_reference(text, authenticated_customer_id)
    if cross_customer_hits:
        return {
            "decision": "block",
            "reason_code": "cross_customer_reference",
            "details": {"mentions": cross_customer_hits},
        }

    return {"decision": "allow", "reason_code": None, "details": {}}
