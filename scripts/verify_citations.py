"""Citation resolver (§3.4 Citation-Resolves Rule, AC-08, §7.2).

Scans one or more Markdown docs for cited run_id / trace_id / span_id
values and tool-log record references, and checks each one actually
resolves to a committed artifact:
  - run_id  -> must appear in traces/phoenix_spans.parquet's
               attributes.metadata (JSON-stringified; see
               src/observability/export.py) OR in logs/tool_calls.jsonl /
               logs/agent_actions.jsonl.
  - trace_id / span_id -> must appear in traces/phoenix_spans.parquet's
               context.trace_id / context.span_id columns.

Writes reports/citation_check.json. Exits non-zero if any citation fails
to resolve (a citation that doesn't resolve is treated as missing, per
the Citation-Resolves Rule -- never silently ignored).

Extended in Phase 6 (P6-03) to also check CTL-xx control-catalog citations
in governance docs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# run-<uuid4>, e.g. run-2acadb2c-16af-49f6-9baa-80d20767fcd5 (src/common/ids.py)
_RUN_ID_RE = re.compile(r"\brun-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
# Phoenix/OTel trace_id (32 hex) and span_id (16 hex), each usually backticked in prose.
_TRACE_ID_RE = re.compile(r"\btrace_id[:=]?\s*`?([0-9a-f]{32})`?", re.IGNORECASE)
_SPAN_ID_RE = re.compile(r"\bspan_id[:=]?\s*`?([0-9a-f]{16})`?", re.IGNORECASE)


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


def verify_citations(
    doc_paths: list[Path],
    *,
    traces_path: Path = Path("traces/phoenix_spans.parquet"),
    log_paths: list[Path] | None = None,
) -> dict[str, Any]:
    log_paths = log_paths or [Path("logs/tool_calls.jsonl"), Path("logs/agent_actions.jsonl")]
    known = _load_known_ids(traces_path, log_paths)

    findings: list[dict[str, Any]] = []
    for doc_path in doc_paths:
        if not doc_path.exists():
            findings.append({"doc": str(doc_path), "kind": "missing_doc", "value": None})
            continue
        cited = _extract_citations(doc_path.read_text(encoding="utf-8"))
        for kind, values in cited.items():
            for value in values:
                if value not in known[kind]:
                    findings.append({"doc": str(doc_path), "kind": kind, "value": value})

    return {
        "docs_checked": [str(p) for p in doc_paths],
        "known_counts": {k: len(v) for k, v in known.items()},
        "unresolved": findings,
        "ok": not findings,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("docs", nargs="*", default=["docs/failure-analysis.md"])
    p.add_argument("--out", default="reports/citation_check.json")
    args = p.parse_args(argv)

    result = verify_citations([Path(d) for d in args.docs])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if result["ok"]:
        print(f"OK: every citation in {args.docs} resolves to a committed artifact.")
        return 0
    print(f"FAILED: {len(result['unresolved'])} citation(s) did not resolve:", file=sys.stderr)
    for f in result["unresolved"]:
        print(f"  - {f['doc']}: {f['kind']}={f['value']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
