"""Tests for scripts/verify_submission.py (ref-doc.md §7 checklist, NFR-07).

Offline: every case builds a tiny fake repository under tmp_path.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

import scripts.verify_submission as v


def _touch_all_required(root: Path) -> None:
    for _section, rel, is_dir, _required in v.REQUIRED_PATHS:
        path = root / rel
        if is_dir:
            path.mkdir(parents=True, exist_ok=True)
            (path / "x.py").write_text("x", encoding="utf-8")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("data", encoding="utf-8")


def _by_name(checks: list[v.Check]) -> dict[str, v.Check]:
    return {c.name: c for c in checks}


def test_all_required_paths_present_passes(tmp_path):
    _touch_all_required(tmp_path)
    assert all(c.ok for c in v.check_required_paths(tmp_path))


def test_missing_and_empty_paths_fail_but_the_optional_api_does_not(tmp_path):
    _touch_all_required(tmp_path)
    (tmp_path / "docs/compliance.md").unlink()
    (tmp_path / "README.md").write_text("", encoding="utf-8")
    import shutil

    shutil.rmtree(tmp_path / "src/api")
    checks = _by_name(v.check_required_paths(tmp_path))
    assert not checks["path docs/compliance.md"].ok and checks["path docs/compliance.md"].detail == "missing"
    assert not checks["path README.md"].ok and checks["path README.md"].detail == "empty"
    assert checks["path src/api (optional)"].ok


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_jsonl_schemas_pass_with_required_fields_and_fail_without(tmp_path):
    good_tool = dict.fromkeys(v.TOOL_CALL_FIELDS, 1)
    good_audit = dict.fromkeys(v.AUDIT_FIELDS, 1)
    good_mcp = dict.fromkeys(v.MCP_FIELDS, 1)
    _write_jsonl(tmp_path / "logs/tool_calls.jsonl", [good_tool])
    _write_jsonl(tmp_path / "logs/agent_actions.jsonl", [good_audit])
    _write_jsonl(tmp_path / "logs/mcp_transcript.jsonl", [good_mcp])
    assert all(c.ok for c in v.check_jsonl_schemas(tmp_path))

    bad_tool = {k: 1 for k in v.TOOL_CALL_FIELDS if k != "latency_ms"}
    _write_jsonl(tmp_path / "logs/tool_calls.jsonl", [good_tool, bad_tool])
    result = _by_name(v.check_jsonl_schemas(tmp_path))["jsonl logs/tool_calls.jsonl"]
    assert not result.ok and "line 2" in result.detail


def test_jsonl_missing_empty_or_invalid_fails(tmp_path):
    assert not v._check_fields(tmp_path, "logs/none.jsonl", {"a"}, "x").ok
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/empty.jsonl").write_text("", encoding="utf-8")
    assert not v._check_fields(tmp_path, "logs/empty.jsonl", {"a"}, "x").ok
    (tmp_path / "logs/bad.jsonl").write_text("{not json}\n", encoding="utf-8")
    assert "invalid JSON" in v._check_fields(tmp_path, "logs/bad.jsonl", {"a"}, "x").detail


def _spans(names: list[str], *, with_times: bool = True) -> pd.DataFrame:
    t = pd.Timestamp("2026-01-01")
    return pd.DataFrame(
        {
            "name": names,
            "start_time": [t] * len(names) if with_times else [None] * len(names),
            "end_time": [t + pd.Timedelta(seconds=1)] * len(names),
            "attributes.metadata": [json.dumps({"run_id": "run-1"})] * len(names),
        }
    )


def _trace_repo(tmp_path: Path, names: list[str], *, with_times: bool = True) -> None:
    (tmp_path / "traces").mkdir(exist_ok=True)
    _spans(names, with_times=with_times).to_parquet(tmp_path / "traces/phoenix_spans.parquet")
    _write_jsonl(tmp_path / "logs/tool_calls.jsonl", [{"tool_name": "get_account_balance"}])


def test_trace_export_needs_supervisor_workers_tool_spans_and_latencies(tmp_path):
    names = ["supervisor", "intake", "account_servicing", "dispute", "get_account_balance"]
    _trace_repo(tmp_path, names)
    assert v.check_trace_export(tmp_path)[0].ok


def test_trace_export_fails_for_too_few_agents_or_null_latency(tmp_path):
    _trace_repo(tmp_path, ["supervisor", "intake", "get_account_balance"])
    assert not v.check_trace_export(tmp_path)[0].ok
    names = ["supervisor", "intake", "account_servicing", "dispute", "get_account_balance"]
    _trace_repo(tmp_path, names, with_times=False)
    assert "null start_time" in v.check_trace_export(tmp_path)[0].detail


def _golden(cost: float | None = 0.44) -> dict:
    return {
        "latency_by_class": {c: {"p50_ms": 1, "p95_ms": 2} for c in ("thinking", "acting", "tool")},
        "tokens": {"input_tokens": 1, "output_tokens": 1},
        "cost": {"total_usd": cost},
        "accuracy": 0.6,
        "hallucination_rate": 0.0,
    }


def _eval(judge: str = "gemini-3.1-flash-lite") -> dict:
    return {
        "metadata": {"judge_model": judge},
        "metrics": {"accuracy": 0.6, "hallucination_rate": 0.0, "faithfulness_mean": 0.9, "answer_relevancy_mean": 0.7, "case_count": 30},
        "results": [{"id": "g-1"}],
    }


def _reports(tmp_path: Path, golden: dict, evaluation: dict) -> None:
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports/golden_signals.json").write_text(json.dumps(golden), encoding="utf-8")
    (tmp_path / "reports/eval_report.json").write_text(json.dumps(evaluation), encoding="utf-8")


def test_report_keys_pass_for_complete_reports(tmp_path):
    _reports(tmp_path, _golden(), _eval())
    assert all(c.ok for c in v.check_report_keys(tmp_path))


def test_null_cost_and_non_gemini_judge_fail(tmp_path):
    _reports(tmp_path, _golden(cost=None), _eval(judge="gpt-4"))
    checks = _by_name(v.check_report_keys(tmp_path))
    assert "cost.total_usd is null" in checks["golden_signals keys"].detail
    assert "not recorded as a Gemini model" in checks["eval_report keys"].detail


def test_agent_tests_need_at_least_one_test_function(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_routing.py").write_text("async def test_a():\n    pass\ndef test_b():\n    pass\n", encoding="utf-8")
    (tmp_path / "tests/test_loops.py").write_text("x = 1\n", encoding="utf-8")
    checks = _by_name(v.check_agent_tests(tmp_path))
    assert checks["tests tests/test_routing.py"].ok and "2 test" in checks["tests tests/test_routing.py"].detail
    assert not checks["tests tests/test_loops.py"].ok
    assert not checks["tests tests/test_tool_contracts.py"].ok


def test_governance_docs_need_their_section_keywords(tmp_path):
    (tmp_path / "docs").mkdir()
    for rel, words in v.GOVERNANCE_KEYWORDS.items():
        (tmp_path / rel).write_text(" ".join(words), encoding="utf-8")
    assert all(c.ok for c in v.check_governance_docs(tmp_path))
    (tmp_path / "docs/risk-register.md").write_text("risk only", encoding="utf-8")
    assert "missing" in _by_name(v.check_governance_docs(tmp_path))["governance docs/risk-register.md"].detail


def test_scan_reports_must_say_ok(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/secrets_scan.json").write_text(json.dumps({"tree_findings": [], "history_findings": [], "ok": True}), encoding="utf-8")
    (tmp_path / "reports/pii_scan.json").write_text(json.dumps({"findings": [{"kind": "card"}], "ok": False}), encoding="utf-8")
    checks = _by_name(v.check_scan_reports(tmp_path))
    assert checks["secrets scan"].ok
    assert not checks["evidence PII scan"].ok and "1 finding" in checks["evidence PII scan"].detail


def test_container_files_are_flagged(tmp_path):
    assert v.check_no_container_files(tmp_path)[0].ok
    (tmp_path / "Dockerfile").write_text("FROM scratch", encoding="utf-8")
    assert not v.check_no_container_files(tmp_path)[0].ok
    (tmp_path / "Dockerfile").unlink()
    (tmp_path / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
    assert not v.check_no_container_files(tmp_path)[0].ok


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=root, check=True, capture_output=True)


def _commit(root: Path, name: str) -> None:
    (root / name).write_text(name, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", name)


def _repo_with_merges(root: Path, merges: int, *, direct_commit: bool = False) -> None:
    _git(root, "init", "-q", "-b", "main")
    _commit(root, "root")
    for i in range(merges):
        _git(root, "checkout", "-q", "-b", f"phase-{i}")
        _commit(root, f"work{i}")
        _git(root, "checkout", "-q", "main")
        _git(root, "merge", "-q", "--no-ff", "-m", f"merge {i}", f"phase-{i}")
    if direct_commit:
        _commit(root, "direct")


def test_git_merges_pass_with_three_no_ff_merges(tmp_path):
    _repo_with_merges(tmp_path, 3)
    assert v.check_git_merges(tmp_path)[0].ok


def test_git_merges_fail_with_too_few_merges_or_a_direct_commit(tmp_path):
    _repo_with_merges(tmp_path, 2)
    assert not v.check_git_merges(tmp_path)[0].ok
    other = tmp_path / "other"
    other.mkdir()
    _repo_with_merges(other, 3, direct_commit=True)
    result = v.check_git_merges(other)[0]
    assert not result.ok and "1 direct commit" in result.detail


def test_git_merges_reports_a_missing_ref(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "trunk")
    assert not v.check_git_merges(tmp_path, ref="main")[0].ok


def test_manifest_records_sha256_size_and_producing_command(tmp_path):
    _touch_all_required(tmp_path)
    manifest = v.build_manifest(tmp_path)
    entry = next(a for a in manifest["artifacts"] if a["path"] == "reports/golden_signals.json")
    assert entry["sha256"] == hashlib.sha256(b"data").hexdigest()
    assert entry["bytes"] == 4
    assert "golden_signals" in entry["produced_by"]
    assert manifest["artifact_count"] == len(manifest["artifacts"]) > 20
    assert all(a["path"] != "mcp_server" for a in manifest["artifacts"])  # directories are not hashed
