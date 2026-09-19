"""Evidence PII scanner: logs, traces, reports, docs (NFR-05, AC-06, §3.4).

Searches everything committed under logs/, traces/, reports/ and docs/ for
Luhn-valid 13-19 digit sequences (unmasked card numbers) and full synthetic
account numbers (``AC`` + 10 digits, unmasked). These shapes should never
appear in evidence: src/common/masking.py and src/guardrails/output.py both
mask them before anything is written to a log, trace or report.

The scan is narrower than a general PII detector (it does not flag names,
emails, etc.) because the concrete, checkable requirement here is "no
plaintext card/account numbers ever land in committed evidence" — the same
digit-shape check the masking helpers themselves use (`luhn_check`), so a
finding here means the masking pipeline was actually bypassed somewhere.

Only the D-14 redaction sample (reports/pii_redaction_sample.json) is
allow-listed: it exists specifically to show a "before" (unmasked) value next
to Presidio's "after" so the redaction pipeline can be demonstrated at all.

Handles the binary traces/*.parquet files by reading them with pandas and
scanning every string cell, rather than raw-byte scanning (nested/dict
columns are JSON-stringified before being written — see
src/observability/export.py — so treating them as plain strings is enough).

Usage:
    python scripts/scan_evidence_for_pii.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.common.masking import luhn_check  # noqa: E402

SCAN_DIRS = ("logs", "traces", "reports", "docs")

# Same digit-run shape the masking helpers use: 13-19 digits, optionally
# separated by spaces/hyphens.
_DIGIT_RUN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_ACCOUNT_NUMBER = re.compile(r"\bAC\d{10}\b")

# The D-14 sample deliberately shows a raw "before" value to demonstrate the
# redaction pipeline (src/guardrails/pii.py) — it is not a masking failure.
ALLOWLISTED_FILES = {"reports/pii_redaction_sample.json"}

TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".log", ".txt", ".csv"}


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def scan_text(text: str, source: str) -> list[dict]:
    findings = []
    for match in _DIGIT_RUN.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if luhn_check(digits):
            findings.append({"kind": "unmasked_pan", "source": source, "last4": digits[-4:]})
    for match in _ACCOUNT_NUMBER.finditer(text):
        findings.append({"kind": "unmasked_account_number", "source": source, "last4": match.group(0)[-4:]})
    return findings


def scan_parquet(path: Path) -> list[dict]:
    import pandas as pd

    df = pd.read_parquet(path)
    findings = []
    for col in df.columns:
        for row_idx, value in df[col].items():
            if isinstance(value, str) and value:
                findings.extend(scan_text(value, f"{_rel(path)}#{col}[{row_idx}]"))
    return findings


def scan_file(path: Path) -> list[dict]:
    if _rel(path) in ALLOWLISTED_FILES:
        return []
    if path.suffix == ".parquet":
        return scan_parquet(path)
    if path.suffix in TEXT_SUFFIXES:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
        return scan_text(text, _rel(path))
    return []


def scan_evidence() -> list[dict]:
    findings: list[dict] = []
    for dirname in SCAN_DIRS:
        base = _REPO_ROOT / dirname
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                findings.extend(scan_file(path))
    return findings


def main() -> int:
    reports_dir = _REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    findings = scan_evidence()
    result = {
        "scanned_dirs": list(SCAN_DIRS),
        "allowlisted_files": sorted(ALLOWLISTED_FILES),
        "findings": findings,
        "ok": not findings,
    }
    (reports_dir / "pii_scan.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"evidence PII scan: {len(findings)} finding(s) across {', '.join(SCAN_DIRS)}")
    if findings:
        print("FAIL:")
        for f in findings:
            print(f"  - {f['kind']} in {f['source']} (last4={f['last4']})")
        return 1
    print("OK: no unmasked card/account numbers found in committed evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
