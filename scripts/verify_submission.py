"""Submission verifier for the ref-doc.md section 7 checklist (§3.4 Evidence-in-Repo
Rule, §7, NFR-06, NFR-07).

Checks that every required artifact exists, is non-empty and has the content the
brief asks for, then writes ``reports/evidence_manifest.json`` (sha256, size, the
command that produces it and the last commit that touched it for each artifact).
Exits non-zero if any check fails, so a gap is never silently submitted.

Checks:
  paths       every section 7 path exists and is non-empty (src/api/ is optional)
  jsonl       required fields on logs/tool_calls.jsonl, logs/agent_actions.jsonl,
              logs/mcp_transcript.jsonl (§7.2, §7.4, §7.1)
  traces      the parquet has the supervisor and >= 3 workers, a span for every
              logged tool, non-null latencies and run ids (reuses verify_trace_export)
  reports     golden_signals.json and eval_report.json carry the required keys and
              a real cost, accuracy and hallucination rate (§7.3, §7.6)
  tests       the three agent test files exist and contain tests (§7.6)
  governance  the four governance docs have the sections the brief lists (§7.5)
  citations   every citation in the failure and governance docs resolves
  scans       the committed secrets and evidence-PII scan reports are clean
  containers  no Dockerfile or compose file is tracked (§6.2)
  merges      (--check-git-merges) main has >= 3 --no-ff merges and no direct commits
              (§7.7, NFR-07); needs the remote history, so it is opt-in

Usage:
    python scripts/verify_submission.py [--check-git-merges] [--out PATH | --no-manifest]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# (ref-doc section, path, is_directory, required)
REQUIRED_PATHS: list[tuple[str, str, bool, bool]] = [
    ("7.1", "src/graph.py", False, True),
    ("7.1", "mcp_server", True, True),
    ("7.1", "logs/mcp_transcript.jsonl", False, True),
    ("7.1", "src/context", True, True),
    ("7.1", "src/memory", True, True),
    ("7.1", "tests/test_memory_persistence.py", False, True),
    ("7.1", "logs/memory_test.log", False, True),
    ("7.1", "src/tools/rag_tool.py", False, True),
    ("7.1", "data/policy_corpus", True, True),
    ("7.2", "src/observability/tracing.py", False, True),
    ("7.2", "traces/phoenix_spans.parquet", False, True),
    ("7.2", "logs/tool_calls.jsonl", False, True),
    ("7.2", "docs/failure-analysis.md", False, True),
    ("7.3", "reports/golden_signals.json", False, True),
    ("7.3", "src/observability/golden_signals.py", False, True),
    ("7.3", "reports/dashboard.png", False, True),
    ("7.3", "reports/dashboard_data.csv", False, True),
    ("7.4", "src/guardrails", True, True),
    ("7.4", "logs/agent_actions.jsonl", False, True),
    ("7.4", ".env.example", False, True),
    ("7.4", ".gitignore", False, True),
    ("7.5", "docs/risk-register.md", False, True),
    ("7.5", "docs/model-card.md", False, True),
    ("7.5", "docs/compliance.md", False, True),
    ("7.5", "docs/output-risk.md", False, True),
    ("7.6", "reports/eval_report.json", False, True),
    ("7.6", "src/evaluation/harness.py", False, True),
    ("7.6", "tests/test_routing.py", False, True),
    ("7.6", "tests/test_loops.py", False, True),
    ("7.6", "tests/test_tool_contracts.py", False, True),
    ("7.7", "README.md", False, True),
    ("7.7", "src/api", True, False),  # bonus, optional
]

# How each evidence artifact is produced (mirrors the README table).
PRODUCING_COMMANDS: dict[str, str] = {
    "logs/mcp_transcript.jsonl": "python -m src.cli mcp-demo",
    "logs/memory_test.log": "pytest tests/test_memory_persistence.py -m live -q",
    "traces/phoenix_spans.parquet": "python -m src.cli export --parquet traces/phoenix_spans.parquet",
    "logs/tool_calls.jsonl": "python -m src.cli regenerate --traces --commit-evidence",
    "logs/agent_actions.jsonl": "python -m src.cli regenerate --traces --commit-evidence",
    "docs/failure-analysis.md": "hand-written from Phoenix traces; checked by python scripts/verify_citations.py",
    "reports/golden_signals.json": "python -m src.observability.golden_signals --eval reports/eval_report_initial.json --out reports/golden_signals.json",
    "reports/dashboard.png": "screenshot of the local Phoenix UI (python -m src.cli regenerate --traces --keep-ui)",
    "reports/dashboard_data.csv": "python -m src.cli export --csv reports/dashboard_data.csv",
    "docs/risk-register.md": "hand-written; checked by python scripts/verify_citations.py",
    "docs/model-card.md": "hand-written; checked by python scripts/verify_citations.py",
    "docs/compliance.md": "hand-written; checked by python scripts/verify_citations.py",
    "docs/output-risk.md": "hand-written from reports/output_risk_sample.json",
    "reports/eval_report.json": "python -m src.cli eval --out reports/eval_report.json",
}

TOOL_CALL_FIELDS = {"timestamp", "agent", "tool_name", "args", "result", "latency_ms", "status"}
AUDIT_FIELDS = {"actor", "action", "tool", "decision", "timestamp"}
MCP_FIELDS = {"timestamp", "name", "status"}
AGENT_TESTS = ["tests/test_routing.py", "tests/test_loops.py", "tests/test_tool_contracts.py"]
CITATION_DOCS = [
    "docs/failure-analysis.md",
    "docs/risk-register.md",
    "docs/model-card.md",
    "docs/compliance.md",
    "docs/output-risk.md",
    "docs/security-approach.md",
]
# Keywords each governance doc must contain (case-insensitive), per §7.5.
GOVERNANCE_KEYWORDS: dict[str, list[str]] = {
    "docs/risk-register.md": ["risk", "category", "likelihood", "impact", "mitigation", "residual", "owner"],
    "docs/model-card.md": ["gemini", "synthetic", "intended use", "limitations", "failure", "out-of-scope"],
    "docs/compliance.md": ["eu ai act", "nist ai rmf", "dpdp", "evidence"],
    "docs/output-risk.md": ["low", "medium", "high", "human", "sample"],
}


@dataclass
class Check:
    section: str
    name: str
    ok: bool
    detail: str = ""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _tracked(root: Path) -> set[str] | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True, encoding="utf-8"
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}


# ------------------------------------------------------------------- checks


def check_required_paths(root: Path) -> list[Check]:
    checks = []
    for section, rel, is_dir, required in REQUIRED_PATHS:
        path = root / rel
        if is_dir:
            files = [f for f in path.rglob("*") if f.is_file() and f.stat().st_size > 0 and "__pycache__" not in f.parts] if path.is_dir() else []
            ok, detail = bool(files), f"{len(files)} non-empty file(s)"
        else:
            ok = path.is_file() and path.stat().st_size > 0
            detail = f"{path.stat().st_size} bytes" if path.is_file() else "missing"
        if not ok and not required:
            checks.append(Check(section, f"path {rel} (optional)", True, "absent (optional bonus)"))
        else:
            checks.append(Check(section, f"path {rel}", ok, detail if ok else (detail if not path.exists() else "empty")))
    return checks


def _check_fields(root: Path, rel: str, fields: set[str], section: str) -> Check:
    path = root / rel
    if not path.is_file():
        return Check(section, f"jsonl {rel}", False, "missing")
    try:
        rows = _read_jsonl(path)
    except json.JSONDecodeError as exc:
        return Check(section, f"jsonl {rel}", False, f"invalid JSON line: {exc}")
    if not rows:
        return Check(section, f"jsonl {rel}", False, "no records")
    bad = [i for i, r in enumerate(rows, 1) if not fields <= set(r)]
    if bad:
        return Check(section, f"jsonl {rel}", False, f"{len(bad)} record(s) missing fields {sorted(fields)} (first: line {bad[0]})")
    return Check(section, f"jsonl {rel}", True, f"{len(rows)} records with all required fields")


def check_jsonl_schemas(root: Path) -> list[Check]:
    return [
        _check_fields(root, "logs/tool_calls.jsonl", TOOL_CALL_FIELDS, "7.2"),
        _check_fields(root, "logs/agent_actions.jsonl", AUDIT_FIELDS, "7.4"),
        _check_fields(root, "logs/mcp_transcript.jsonl", MCP_FIELDS, "7.1"),
    ]


def check_trace_export(root: Path) -> list[Check]:
    import pandas as pd

    import scripts.verify_trace_export as vte

    path = root / "traces/phoenix_spans.parquet"
    if not path.is_file():
        return [Check("7.2", "traces parquet", False, "missing")]
    df = pd.read_parquet(path)
    names = set(df["name"].dropna()) if "name" in df.columns else set()
    problems = [
        *vte.check_multi_agent_coverage(names),
        *vte.check_tool_call_coverage(names, vte._tool_names_from_log(root / "logs/tool_calls.jsonl")),
        *vte.check_latencies_present(df),
        *vte.check_run_id_present(df),
    ]
    detail = f"{len(df)} spans, {len(names)} distinct names"
    return [Check("7.2", "traces parquet coverage", not problems, detail if not problems else "; ".join(problems))]


def check_report_keys(root: Path) -> list[Check]:
    checks = []
    gs_path = root / "reports/golden_signals.json"
    if not gs_path.is_file():
        checks.append(Check("7.3", "golden_signals keys", False, "missing"))
    else:
        gs = json.loads(gs_path.read_text(encoding="utf-8"))
        problems = []
        for cls in ("thinking", "acting", "tool"):
            lat = gs.get("latency_by_class", {}).get(cls, {})
            if "p50_ms" not in lat or "p95_ms" not in lat:
                problems.append(f"latency_by_class.{cls} lacks p50_ms/p95_ms")
        tokens = gs.get("tokens", {})
        if "input_tokens" not in tokens or "output_tokens" not in tokens:
            problems.append("tokens lacks input/output totals")
        if (gs.get("cost") or {}).get("total_usd") is None:
            problems.append("cost.total_usd is null (a cost estimate is required)")
        for key in ("accuracy", "hallucination_rate"):
            if gs.get(key) is None:
                problems.append(f"{key} is missing")
        checks.append(Check("7.3", "golden_signals keys", not problems, "; ".join(problems) or "latency split, tokens, cost, accuracy, hallucination_rate present"))

    ev_path = root / "reports/eval_report.json"
    if not ev_path.is_file():
        checks.append(Check("7.6", "eval_report keys", False, "missing"))
    else:
        ev = json.loads(ev_path.read_text(encoding="utf-8"))
        problems = []
        metrics = ev.get("metrics", {})
        for key in ("accuracy", "hallucination_rate", "faithfulness_mean", "answer_relevancy_mean"):
            if metrics.get(key) is None:
                problems.append(f"metrics.{key} missing")
        if not ev.get("results"):
            problems.append("no per-case results")
        if "gemini" not in str(ev.get("metadata", {}).get("judge_model", "")).lower():
            problems.append("judge model is not recorded as a Gemini model")
        checks.append(Check("7.6", "eval_report keys", not problems, "; ".join(problems) or f"{metrics.get('case_count')} cases, Gemini judge, all metrics present"))
    return checks


def check_agent_tests(root: Path) -> list[Check]:
    checks = []
    for rel in AGENT_TESTS:
        path = root / rel
        count = len(re.findall(r"^\s*(?:async\s+)?def test_", path.read_text(encoding="utf-8"), re.M)) if path.is_file() else 0
        checks.append(Check("7.6", f"tests {rel}", count > 0, f"{count} test function(s)" if count else "missing or no tests"))
    return checks


def check_governance_docs(root: Path) -> list[Check]:
    checks = []
    for rel, keywords in GOVERNANCE_KEYWORDS.items():
        path = root / rel
        if not path.is_file():
            checks.append(Check("7.5", f"governance {rel}", False, "missing"))
            continue
        text = path.read_text(encoding="utf-8").lower()
        missing = [k for k in keywords if k not in text]
        checks.append(Check("7.5", f"governance {rel}", not missing, f"missing: {missing}" if missing else "required sections present"))
    return checks


def check_citations(root: Path) -> list[Check]:
    import scripts.verify_citations as vc

    docs = [root / d for d in CITATION_DOCS if (root / d).exists()]
    result = vc.verify_citations(
        docs,
        traces_path=root / "traces/phoenix_spans.parquet",
        log_paths=[root / "logs/tool_calls.jsonl", root / "logs/agent_actions.jsonl"],
        catalog_path=root / "docs/control-catalog.md",
        root=root,
    )
    detail = f"{len(docs)} docs, {result['controls_checked']} controls"
    if result["ok"]:
        return [Check("3.4", "citations resolve", True, detail)]
    first = "; ".join(f"{f['kind']}={f['value']}" for f in result["unresolved"][:4])
    return [Check("3.4", "citations resolve", False, f"{len(result['unresolved'])} unresolved ({first} ...)")]


def check_scan_reports(root: Path) -> list[Check]:
    checks = []
    for rel, label in (("reports/secrets_scan.json", "secrets scan"), ("reports/pii_scan.json", "evidence PII scan")):
        path = root / rel
        if not path.is_file():
            checks.append(Check("7.4", label, False, f"{rel} missing"))
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        findings = len(data.get("findings", [])) or len(data.get("tree_findings", [])) + len(data.get("history_findings", []))
        checks.append(Check("7.4", label, bool(data.get("ok")), "clean" if data.get("ok") else f"report says not ok ({findings} finding(s)); re-run the scanner"))
    return checks


def check_no_container_files(root: Path) -> list[Check]:
    tracked = _tracked(root)
    files = tracked if tracked is not None else {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts}
    pattern = re.compile(r"(^|/)(dockerfile[^/]*|docker-compose[^/]*|compose\.ya?ml|\.dockerignore)$", re.I)
    found = sorted(f for f in files if pattern.search(f))
    return [Check("6.2", "no Docker/compose files", not found, f"found: {found}" if found else "none tracked")]


def check_git_merges(root: Path, ref: str = "main", minimum: int = 3) -> list[Check]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--first-parent", "--format=%H %P", ref],
            capture_output=True, text=True, check=True, encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        return [Check("7.7", f"git merges on {ref}", False, f"cannot read history of {ref}: {type(exc).__name__}")]
    rows = [line.split() for line in out.splitlines() if line.strip()]
    merges = [r for r in rows if len(r) - 1 >= 2]
    direct = [r for r in rows if len(r) - 1 == 1]
    ok = len(merges) >= minimum and not direct
    detail = f"{len(merges)} merge commit(s) (need >= {minimum}), {len(direct)} direct commit(s) on the first-parent line"
    return [Check("7.7", f"git merges on {ref}", ok, detail)]


# ----------------------------------------------------------------- manifest


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _last_commit(root: Path, rel: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%h", "--", rel],
            capture_output=True, text=True, check=True, encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return out or None


def build_manifest(root: Path) -> dict[str, Any]:
    artifacts = []
    for section, rel, is_dir, _required in REQUIRED_PATHS:
        path = root / rel
        if is_dir or not path.is_file():
            continue
        artifacts.append(
            {
                "path": rel,
                "section": section,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "produced_by": PRODUCING_COMMANDS.get(rel, "source code / hand-written"),
                "last_commit": _last_commit(root, rel),
            }
        )
    head = _last_commit(root, ".")
    return {"git_head": head, "artifact_count": len(artifacts), "artifacts": artifacts}


# --------------------------------------------------------------------- main


def run_all(root: Path, *, check_merges: bool = False) -> list[Check]:
    checks: list[Check] = [
        *check_required_paths(root),
        *check_jsonl_schemas(root),
        *check_trace_export(root),
        *check_report_keys(root),
        *check_agent_tests(root),
        *check_governance_docs(root),
        *check_citations(root),
        *check_scan_reports(root),
        *check_no_container_files(root),
    ]
    if check_merges:
        checks += check_git_merges(root)
    return checks


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check-git-merges", action="store_true", help="also verify >= 3 --no-ff merges on main (needs the remote history)")
    p.add_argument("--out", default="reports/evidence_manifest.json")
    p.add_argument("--no-manifest", action="store_true", help="do not write the evidence manifest")
    args = p.parse_args(argv)

    checks = run_all(_REPO_ROOT, check_merges=args.check_git_merges)
    for c in checks:
        print(f"[{'OK  ' if c.ok else 'FAIL'}] {c.section:<4} {c.name}: {c.detail}")
    failed = [c for c in checks if not c.ok]

    if not args.no_manifest:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        manifest = build_manifest(_REPO_ROOT)
        manifest["checks"] = [c.__dict__ for c in checks]
        manifest["ok"] = not failed
        out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {out} ({manifest['artifact_count']} artifacts)")

    if failed:
        print(f"\nFAILED: {len(failed)} of {len(checks)} check(s) did not pass.", file=sys.stderr)
        return 1
    print(f"\nOK: all {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
