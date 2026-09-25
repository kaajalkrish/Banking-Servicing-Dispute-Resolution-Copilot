"""Verify a Phoenix trace export covers the whole multi-agent system (§7.2).

Asserts, against a committed parquet export and the tool-invocation log:
- the supervisor and at least 3 of the 4 workers appear as spans;
- every distinct tool_name in logs/tool_calls.jsonl has a matching span name
  in the export (so "every tool call" really is covered, not just some);
- every span has a non-null latency (start_time and end_time both present);
- at least one span carries a run_id in attributes.metadata (AC-08's citation
  fields are actually populated, not just structurally possible).

Usage:
    python scripts/verify_trace_export.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd

WORKER_NAMES = {"intake", "account_servicing", "dispute", "product_info"}
MIN_WORKERS = 3


def check_multi_agent_coverage(span_names: set[str]) -> list[str]:
    problems = []
    if "supervisor" not in span_names:
        problems.append("no 'supervisor' span found")
    covered = span_names & WORKER_NAMES
    if len(covered) < MIN_WORKERS:
        problems.append(
            f"only {len(covered)} worker span(s) found ({sorted(covered)}); need >= {MIN_WORKERS}"
        )
    return problems


def check_tool_call_coverage(span_names: set[str], tool_names_from_log: set[str]) -> list[str]:
    missing = sorted(tool_names_from_log - span_names)
    return [f"tool '{t}' in tool_calls.jsonl has no matching span" for t in missing]


def check_latencies_present(df: pd.DataFrame) -> list[str]:
    if "start_time" not in df.columns or "end_time" not in df.columns:
        return ["parquet is missing start_time/end_time columns"]
    missing = df["start_time"].isna() | df["end_time"].isna()
    if missing.any():
        return [f"{int(missing.sum())} span(s) have a null start_time or end_time"]
    return []


def _metadata_has_run_id(value: object) -> bool:
    """attributes.metadata is a dict on a live dataframe, but export.py's
    _stringify_nested_columns() JSON-encodes dict columns before writing to
    parquet/csv — so the committed export has this as a JSON *string*, not a
    dict. Handle both shapes (a real committed parquet only ever has the
    string form; a raw dataframe fresh off the Phoenix client has the dict
    form) rather than assuming one."""
    if isinstance(value, dict):
        return "run_id" in value
    if isinstance(value, str):
        try:
            return "run_id" in json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return False
    return False


def check_run_id_present(df: pd.DataFrame) -> list[str]:
    if "attributes.metadata" not in df.columns:
        return ["parquet has no attributes.metadata column"]
    found = df["attributes.metadata"].dropna().apply(_metadata_has_run_id)
    if not found.any():
        return ["no span carries a run_id in attributes.metadata"]
    return []


def _tool_names_from_log(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            if "tool_name" in entry:
                names.add(entry["tool_name"])
    return names


def main() -> int:
    parquet_path = _REPO_ROOT / "traces" / "phoenix_spans.parquet"
    tool_calls_path = _REPO_ROOT / "logs" / "tool_calls.jsonl"

    if not parquet_path.exists():
        print(f"FAIL: {parquet_path} does not exist")
        return 1

    df = pd.read_parquet(parquet_path)
    span_names = set(df["name"].dropna()) if "name" in df.columns else set()
    tool_names = _tool_names_from_log(tool_calls_path)

    problems = [
        *check_multi_agent_coverage(span_names),
        *check_tool_call_coverage(span_names, tool_names),
        *check_latencies_present(df),
        *check_run_id_present(df),
    ]

    print(f"spans: {len(df)} | distinct span names: {len(span_names)} | tools in log: {len(tool_names)}")
    if problems:
        print("FAIL:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: multi-agent coverage, tool-call coverage, latencies and run_id all present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
