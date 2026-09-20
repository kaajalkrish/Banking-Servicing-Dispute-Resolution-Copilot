"""Citation resolver (§3.4 Citation-Resolves Rule, AC-08, AC-11, §7.2, §7.5).

Scans Markdown docs and checks that every citation resolves to a committed
artifact:

  Evidence citations (every doc given):
  - run_id  -> must appear in traces/phoenix_spans.parquet's
               attributes.metadata (JSON-stringified; see
               src/observability/export.py) OR in logs/tool_calls.jsonl /
               logs/agent_actions.jsonl.
  - trace_id / span_id -> must appear in traces/phoenix_spans.parquet's
               context.trace_id / context.span_id columns.

  Governance citations (extended in P6-03):
  - every ``CTL-xx`` cited in a doc must exist in docs/control-catalog.md;
  - every backticked repo path in a doc (src/, tests/, reports/, ...) must
    resolve to a COMMITTED file (a git-tracked path; a gitignored or
    untracked file does not count, because only committed artifacts are
    scored). Outside a git repo it falls back to "exists on disk";
  - the catalog itself: every control must name at least one code path that
    exists, every backticked symbol in that cell must appear in the named
    file(s), and every evidence path (or ``type(scope): subject`` commit
    reference) must resolve.

Writes reports/citation_check.json. Exits non-zero if any citation fails to
resolve (a citation that doesn't resolve is treated as missing, per the
Citation-Resolves Rule -- never silently ignored).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# run-<uuid4>, e.g. run-2acadb2c-16af-49f6-9baa-80d20767fcd5 (src/common/ids.py)
_RUN_ID_RE = re.compile(r"\brun-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
# Phoenix/OTel trace_id (32 hex) and span_id (16 hex), each usually backticked in prose.
_TRACE_ID_RE = re.compile(r"\btrace_id[:=]?\s*`?([0-9a-f]{32})`?", re.IGNORECASE)
_SPAN_ID_RE = re.compile(r"\bspan_id[:=]?\s*`?([0-9a-f]{16})`?", re.IGNORECASE)

_CTL_RE = re.compile(r"\bCTL-\d{2,3}\b")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_COMMIT_REF_RE = re.compile(r"^[a-z]+\([\w-]+\): .+")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*")

_REPO_PREFIXES = (
    "src/",
    "scripts/",
    "tests/",
    "docs/",
    "reports/",
    "logs/",
    "traces/",
    "data/",
    "mcp_server/",
    "notes/",  # gitignored *.local.md files live here: citing one must fail
)
_ROOT_FILES = {
    "README.md",
    "ref-doc.md",
    "plan.md",
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "pyproject.toml",
    "pytest.ini",
}

CATALOG_PATH = Path("docs/control-catalog.md")
FAILURE_DOC = Path("docs/failure-analysis.md")
GOVERNANCE_DOCS = [
    Path("docs/risk-register.md"),
    Path("docs/model-card.md"),
    Path("docs/compliance.md"),
    Path("docs/output-risk.md"),
    Path("docs/security-approach.md"),
]


# ---------------------------------------------------------------- evidence ids


def _extract_citations(text: str) -> dict[str, set[str]]:
    return {
        "run_id": set(_RUN_ID_RE.findall(text)),
        "trace_id": set(_TRACE_ID_RE.findall(text)),
        "span_id": set(_SPAN_ID_RE.findall(text)),
    }


def _load_known_ids(traces_path: Path, log_paths: list[Path]) -> dict[str, set[str]]:
    known: dict[str, set[str]] = {"run_id": set(), "trace_id": set(), "span_id": set()}

    if traces_path.exists():
        import pandas as pd

        df = pd.read_parquet(traces_path)
        if "context.trace_id" in df.columns:
            known["trace_id"] |= set(df["context.trace_id"].dropna().astype(str))
        if "context.span_id" in df.columns:
            known["span_id"] |= set(df["context.span_id"].dropna().astype(str))
        if "attributes.metadata" in df.columns:
            for raw in df["attributes.metadata"].dropna():
                # export.py JSON-stringifies dict columns before writing parquet.
                try:
                    meta = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    continue
                run_id = meta.get("run_id") if isinstance(meta, dict) else None
                if run_id:
                    known["run_id"].add(str(run_id))

    for log_path in log_paths:
        if not log_path.exists():
            continue
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            run_id = record.get("run_id")
            if run_id:
                known["run_id"].add(str(run_id))

    return known


# ------------------------------------------------------------ repo path checks


def _tracked_files(root: Path) -> set[str] | None:
    """Git-tracked (committed or staged) paths under ``root``, or None when
    ``root`` is not a git work tree (fall back to the filesystem)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}


def _as_repo_path(token: str) -> str | None:
    """Return the repo-relative path a backticked token refers to, or None if
    the token is not path-shaped (a symbol, a command, a key=value, ...)."""
    tok = token.strip()
    if not tok or any(c in tok for c in " ()=<>"):
        return None
    tok = re.sub(r"::[\w.]+$", "", tok)  # path::symbol
    tok = re.sub(r":\d+(-\d+)?$", "", tok)  # path:line or path:line-line
    tok = tok.rstrip(".,;")
    if tok.startswith(_REPO_PREFIXES) or tok in _ROOT_FILES:
        return tok
    return None


def _path_resolves(path: str, root: Path, tracked: set[str] | None) -> bool:
    if tracked is not None:
        if any(c in path for c in "*?["):
            return any(fnmatch.fnmatch(t, path) for t in tracked)
        if path.endswith("/"):
            return any(t.startswith(path) for t in tracked)
        return path in tracked or any(t.startswith(path + "/") for t in tracked)
    if any(c in path for c in "*?["):
        return any(root.glob(path))
    return (root / path).exists()


def _backticked_paths(text: str) -> set[str]:
    found: set[str] = set()
    for token in _BACKTICK_RE.findall(text):
        path = _as_repo_path(token)
        if path:
            found.add(path)
    return found


def _commit_subject_exists(subject: str, root: Path) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--all", "--fixed-strings", f"--grep={subject}", "--format=%h"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(out.strip())


# --------------------------------------------------------------- control catalog


def parse_control_catalog(catalog_path: Path) -> dict[str, dict[str, str]]:
    """``{"CTL-01": {"control", "code", "evidence"}}`` from the catalog table."""
    controls: dict[str, dict[str, str]] = {}
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| CTL-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        controls[cells[0]] = {"control": cells[1], "code": cells[2], "evidence": cells[3]}
    return controls


def check_control_catalog(
    catalog_path: Path, *, root: Path, tracked: set[str] | None
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    doc = str(catalog_path)
    for ctl_id, cells in parse_control_catalog(catalog_path).items():
        code_paths = sorted(_backticked_paths(cells["code"]))
        if not code_paths:
            findings.append({"doc": doc, "kind": "ctl_code_path", "value": f"{ctl_id}: no code path"})
        code_text = ""
        for path in code_paths:
            if not _path_resolves(path, root, tracked):
                findings.append({"doc": doc, "kind": "ctl_code_path", "value": f"{ctl_id}: {path}"})
                continue
            file = root / path
            if file.is_file():
                code_text += file.read_text(encoding="utf-8", errors="ignore")
        for token in _BACKTICK_RE.findall(cells["code"]):
            if _as_repo_path(token):
                continue
            match = _IDENT_RE.match(token.strip())
            if match and code_text and match.group(0) not in code_text:
                findings.append(
                    {"doc": doc, "kind": "ctl_symbol", "value": f"{ctl_id}: {match.group(0)}"}
                )

        evidence_tokens = _BACKTICK_RE.findall(cells["evidence"])
        evidence_paths = sorted(_backticked_paths(cells["evidence"]))
        commit_refs = [t for t in evidence_tokens if _COMMIT_REF_RE.match(t.strip())]
        if not evidence_paths and not commit_refs:
            findings.append({"doc": doc, "kind": "ctl_evidence", "value": f"{ctl_id}: no evidence"})
        for path in evidence_paths:
            if not _path_resolves(path, root, tracked):
                findings.append({"doc": doc, "kind": "ctl_evidence", "value": f"{ctl_id}: {path}"})
        for subject in commit_refs:
            if not _commit_subject_exists(subject.strip(), root):
                findings.append({"doc": doc, "kind": "ctl_evidence", "value": f"{ctl_id}: commit {subject}"})
    return findings


# ------------------------------------------------------------------ main check


def verify_citations(
    doc_paths: list[Path],
    *,
    traces_path: Path = Path("traces/phoenix_spans.parquet"),
    log_paths: list[Path] | None = None,
    catalog_path: Path | None = CATALOG_PATH,
    root: Path = Path("."),
) -> dict[str, Any]:
    log_paths = log_paths or [Path("logs/tool_calls.jsonl"), Path("logs/agent_actions.jsonl")]
    known = _load_known_ids(traces_path, log_paths)
    tracked = _tracked_files(root)

    known_controls: set[str] = set()
    findings: list[dict[str, Any]] = []
    controls_checked = 0
    if catalog_path is not None:
        if catalog_path.exists():
            catalog = parse_control_catalog(catalog_path)
            known_controls = set(catalog)
            controls_checked = len(catalog)
            findings += check_control_catalog(catalog_path, root=root, tracked=tracked)
        else:
            findings.append({"doc": str(catalog_path), "kind": "missing_doc", "value": None})

    for doc_path in doc_paths:
        if not doc_path.exists():
            findings.append({"doc": str(doc_path), "kind": "missing_doc", "value": None})
            continue
        text = doc_path.read_text(encoding="utf-8")

        for kind, values in _extract_citations(text).items():
            for value in sorted(values):
                if value not in known[kind]:
                    findings.append({"doc": str(doc_path), "kind": kind, "value": value})

        if catalog_path is not None and doc_path != catalog_path:
            for ctl in sorted(set(_CTL_RE.findall(text))):
                if ctl not in known_controls:
                    findings.append({"doc": str(doc_path), "kind": "ctl_unknown", "value": ctl})

        for path in sorted(_backticked_paths(text)):
            if not _path_resolves(path, root, tracked):
                findings.append({"doc": str(doc_path), "kind": "repo_path", "value": path})

    return {
        "docs_checked": [str(p) for p in doc_paths],
        "known_counts": {k: len(v) for k, v in known.items()},
        "controls_checked": controls_checked,
        "unresolved": findings,
        "ok": not findings,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "docs",
        nargs="*",
        help="docs to check (default: the failure analysis plus every governance doc that exists)",
    )
    p.add_argument("--out", default="reports/citation_check.json")
    args = p.parse_args(argv)

    if args.docs:
        docs = [Path(d) for d in args.docs]
    else:
        docs = [FAILURE_DOC] + [d for d in GOVERNANCE_DOCS if d.exists()]

    result = verify_citations(docs)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    checked = ", ".join(result["docs_checked"])
    if result["ok"]:
        print(f"OK: every citation in {checked} (and {result['controls_checked']} catalogued controls) resolves.")
        return 0
    print(f"FAILED: {len(result['unresolved'])} citation(s) did not resolve:", file=sys.stderr)
    for f in result["unresolved"]:
        print(f"  - {f['doc']}: {f['kind']}={f['value']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
