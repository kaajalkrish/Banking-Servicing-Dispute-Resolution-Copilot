"""Prompt-injection detection: policy functions (heuristic patterns), AC-06.

Guardrails-AI's pre-built injection validators require downloading from the
Guardrails Hub registry (an extra network dependency, and one requiring
authentication for some validators) — ref-doc.md's own guardrail-code
description explicitly allows "policy functions" as the fallback where a
validator cannot be installed. This keeps injection detection fully
offline-testable and dependency-free, at the cost of only catching patterns
we've enumerated rather than a learned classifier's broader coverage.
"""

from __future__ import annotations

import re

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore (all|any|previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard (all|any|previous|prior)\s+(instructions|rules)", re.IGNORECASE),
    re.compile(r"forget (all|your)\s+(instructions|rules|training)", re.IGNORECASE),
    re.compile(r"you are now\b", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"reveal your (instructions|prompt|rules|system message)", re.IGNORECASE),
    re.compile(r"print your (instructions|prompt|rules|system message)", re.IGNORECASE),
    re.compile(r"pretend (you are|to be)\b", re.IGNORECASE),
    re.compile(r"act as (if|a)\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bDAN\b"),  # "Do Anything Now" jailbreak persona
    re.compile(r"new instructions?:", re.IGNORECASE),
]


def detect_injection(text: str) -> list[str]:
    """Return the pattern strings that matched, or [] if none did."""
    text = text or ""
    return [p.pattern for p in _INJECTION_PATTERNS if p.search(text)]
