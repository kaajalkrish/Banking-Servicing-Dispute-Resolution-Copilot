"""Secrets scanner: working tree + git history (NFR-01, §7.4 Secrets hygiene).

Flags Google/Gemini-style API keys and generic high-entropy token patterns in
the tracked working tree and in `git log -p`; verifies `.env` is untracked,
`.gitignore` covers it, and `.env.example` carries only placeholder values
(never a real-looking key). Writes reports/secrets_scan.json; exits non-zero
on any finding.

Usage:
    python scripts/check_secrets.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Patterns for known secret shapes. Deliberately conservative (a handful of
# recognisable prefixes/shapes) rather than a generic high-entropy detector,
# to keep false positives low against a small, known codebase.
SECRET_PATTERNS = {
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "google_oauth_token": re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}\b"),
    "generic_gemini_prefixed": re.compile(r"\bAQ\.[0-9A-Za-z_-]{30,}\b"),
    "generic_bearer_secret": re.compile(r"\bsk-[0-9A-Za-z]{20,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
}

# Files/paths never scanned even if somehow present (never should be tracked).
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".phoenix", "node_modules", "artifacts_regen"}
PLACEHOLDER_VALUES = {"", "PASTE_YOUR_GEMINI_API_KEY_HERE", "your_key_here"}


def _run_git(args: list[str]) -> str:
    # Explicit UTF-8 + replace: `git log -p --all` includes binary-file diffs
    # (e.g. traces/phoenix_spans.parquet is tracked), and Windows' default
    # codec (cp1252) crashes on those bytes rather than just mangling them.
    result = subprocess.run(
        ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout or ""


def _tracked_files() -> list[Path]:
    out = _run_git(["ls-files"])
    return [_REPO_ROOT / line for line in out.splitlines() if line.strip()]


def scan_text(text: str, source: str) -> list[dict]:
    findings = []
    for label, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append({"pattern": label, "source": source, "match_prefix": match.group(0)[:8] + "..."})
    return findings


def scan_working_tree() -> list[dict]:
    findings = []
    for path in _tracked_files():
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        findings.extend(scan_text(text, f"tree:{path.relative_to(_REPO_ROOT)}"))
    return findings


def scan_git_history() -> list[dict]:
    log = _run_git(["log", "-p", "--all"])
    return scan_text(log, "git-history")


def check_env_hygiene() -> list[str]:
    problems = []
    tracked = {str(p.relative_to(_REPO_ROOT)) for p in _tracked_files()}
    if ".env" in tracked:
        problems.append(".env is tracked by git (must never be committed)")

    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8") if (_REPO_ROOT / ".gitignore").exists() else ""
    if ".env" not in gitignore:
        problems.append(".gitignore does not cover .env")

    env_example = _REPO_ROOT / ".env.example"
    if env_example.exists():
        for line in env_example.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if key.strip() == "GOOGLE_API_KEY" and value not in PLACEHOLDER_VALUES and not value.startswith("gemini"):
                # A real-looking key value (not a placeholder, not a model name
                # reference) would be a serious problem in a committed file.
                if any(p.search(value) for p in SECRET_PATTERNS.values()):
                    problems.append(f".env.example line for {key} looks like a real secret, not a placeholder")
    return problems


def main() -> int:
    reports_dir = _REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    tree_findings = scan_working_tree()
    history_findings = scan_git_history()
    env_problems = check_env_hygiene()

    result = {
        "tree_findings": tree_findings,
        "history_findings": history_findings,
        "env_hygiene_problems": env_problems,
        "ok": not tree_findings and not history_findings and not env_problems,
    }
    (reports_dir / "secrets_scan.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"tree findings: {len(tree_findings)} | history findings: {len(history_findings)} | env problems: {len(env_problems)}")
    if not result["ok"]:
        print("FAIL:")
        for f in tree_findings:
            print(f"  - secret-shaped value in {f['source']} ({f['pattern']})")
        for f in history_findings:
            print(f"  - secret-shaped value in git history ({f['pattern']})")
        for p in env_problems:
            print(f"  - {p}")
        return 1
    print("OK: no secrets found in tree/history; .env hygiene verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
