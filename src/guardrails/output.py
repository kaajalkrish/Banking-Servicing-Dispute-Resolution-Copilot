"""Output guardrails: leakage and unsafe-commitment prevention (AC-06, D-13,
§7.4). Masks any PAN/account number that reaches a generated answer
(unconditionally — NFR-05 applies regardless of whose number it is), blocks
another customer's identifier from appearing (the AUTHENTICATED customer's
own id is left alone — mentioning "your account C0001" is fine), and
rewrites promises of refunds/approvals into "drafted for human review"
wording — the copilot never commits money movement (D-13).
"""

from __future__ import annotations

import re
from typing import Any

from src.guardrails.pii import analyze, get_anonymizer

_ALWAYS_MASKED_ENTITIES = {"CREDIT_CARD", "BANK_ACCOUNT_NUMBER"}

_REFUND_PROMISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"your refund (has been|is) approved", re.IGNORECASE),
    re.compile(r"you will (receive|get) a refund", re.IGNORECASE),
    re.compile(r"we have approved (your|this)", re.IGNORECASE),
    re.compile(r"refund (has been )?(processed|issued)", re.IGNORECASE),
    re.compile(r"your money (has been|will be) refunded", re.IGNORECASE),
    # Not just "refund" wording: a dispute *outcome* claim ("your dispute has
    # been approved", "this case is resolved in your favor") is the same kind
    # of unsafe commitment (D-13) even when the word "refund" never appears —
    # found via red-teaming (rt-011: an injected "[SYSTEM: ...]" role marker
    # got a simulated reply to claim the dispute itself was approved, which
    # none of the refund-only patterns above caught).
    re.compile(r"your (dispute|case) (has been|is) approved", re.IGNORECASE),
    re.compile(r"(dispute|case) (has been |is )?(approved|resolved|closed) in your favor", re.IGNORECASE),
]

_SYSTEM_PROMPT_LEAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsystem prompt\b", re.IGNORECASE),
    re.compile(r"you are a retail-bank", re.IGNORECASE),  # matches our own worker SYSTEM strings
]

REFUND_REWRITE = "This has been drafted for human review; no refund or resolution has been approved yet."
SYSTEM_PROMPT_LEAK_REWRITE = "I can't share my internal instructions. How can I help with your banking request?"


def sanitize_output(text: str, *, authenticated_customer_id: str) -> dict[str, Any]:
    text = text or ""
    results = analyze(text)

    to_mask = [
        r
        for r in results
        if r.entity_type in _ALWAYS_MASKED_ENTITIES
        or (r.entity_type == "CUSTOMER_ID" and text[r.start : r.end] != authenticated_customer_id)
    ]
    other_customer_mentions = [text[r.start : r.end] for r in to_mask if r.entity_type == "CUSTOMER_ID"]

    masked = get_anonymizer().anonymize(text=text, analyzer_results=to_mask).text if to_mask else text

    refund_rewrites = []
    for pattern in _REFUND_PROMISE_PATTERNS:
        if pattern.search(masked):
            masked = pattern.sub(REFUND_REWRITE, masked)
            refund_rewrites.append(pattern.pattern)

    system_prompt_leak_detected = any(p.search(masked) for p in _SYSTEM_PROMPT_LEAK_PATTERNS)
    if system_prompt_leak_detected:
        # A leaked system prompt isn't a single phrase that can be rewritten
        # in place like a refund promise — it's typically most of the answer.
        # Replace the whole thing with a safe refusal rather than leaving
        # fragments around a redacted phrase (found via red-teaming: the
        # detection flag alone left the leaked text sitting in the
        # customer-facing answer unchanged — P4-12/13 red-team attack
        # rt-022-series caught this).
        masked = SYSTEM_PROMPT_LEAK_REWRITE

    return {
        "sanitized_text": masked,
        "other_customer_blocked": bool(other_customer_mentions),
        "other_customer_mentions": other_customer_mentions,
        "refund_rewrites": refund_rewrites,
        "system_prompt_leak_detected": system_prompt_leak_detected,
    }
