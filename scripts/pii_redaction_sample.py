"""PII redaction before/after sample generator (§8.1, D-14, NFR-05).

Runs Presidio-based redaction (src/guardrails/pii.py) on a handful of
representative customer messages and writes reports/pii_redaction_sample.json
with each message's raw "before" text, Presidio's raw detections, and the
anonymized "after" text -- demonstrating the redaction middleware for real,
not just describing it.

This is the one deliberately-allow-listed file for scripts/scan_evidence_for_pii.py
(reports/pii_redaction_sample.json): its whole purpose is to show a raw
"before" value next to Presidio's "after", so it necessarily contains
unmasked synthetic PII by design.

Usage:
    python scripts/pii_redaction_sample.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.guardrails.pii import anonymize_text, detect_pii  # noqa: E402

# All values are synthetic (from data/synthetic/accounts.json's shapes and
# fabricated contact details) -- never real customer data (§3.4 Synthetic-
# Data Rule).
SAMPLE_MESSAGES = [
    "My card number is 4000009083863798, can you check my balance?",
    "Please debit account AC1001571945 for the payment I set up yesterday.",
    "Can you check on customer C0002 for me? He asked me to follow up.",
    "Please email me at jane.doe@example.com or call 555-123-4567 to confirm the dispute.",
    "What is the overdraft fee for a checking account?",
]


def build_samples() -> list[dict]:
    samples = []
    for text in SAMPLE_MESSAGES:
        detections = detect_pii(text)
        samples.append(
            {
                "before": text,
                "detections": detections,
                "after": anonymize_text(text),
                "had_pii": bool(detections),
            }
        )
    return samples


def main() -> int:
    reports_dir = _REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    samples = build_samples()
    (reports_dir / "pii_redaction_sample.json").write_text(
        json.dumps(samples, indent=2) + "\n", encoding="utf-8"
    )

    for s in samples:
        print(f"before: {s['before']}")
        print(f"after:  {s['after']}")
        print(f"detections: {[d['entity_type'] for d in s['detections']]}")
        print()

    print(f"wrote {len(samples)} samples to reports/pii_redaction_sample.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
