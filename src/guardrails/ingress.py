"""Ingress sanitizer: mask PAN/account numbers/PII at the earliest boundary
(D-10, AC-06, NFR-05) — before customer input ever reaches the graph, a span,
a prompt, or a log. Wired into the CLI's/API's entry point in P4-09, so no
downstream code (worker prompts, tracing, tool_calls.jsonl) ever sees an
unmasked value from what a customer typed.
"""

from __future__ import annotations

from typing import Any

from src.guardrails.pii import anonymize_text, detect_pii


def sanitize_ingress(text: str) -> dict[str, Any]:
    """Detect and mask PII in raw customer text before graph entry.

    Returns the sanitized text plus the detections found (for audit), and
    whether any PII was present. If nothing was detected, the original text
    is returned unchanged (avoids Presidio's anonymizer touching text it
    didn't need to).
    """
    detections = detect_pii(text)
    sanitized = anonymize_text(text) if detections else text
    return {
        "sanitized_text": sanitized,
        "detections": detections,
        "had_pii": bool(detections),
    }
