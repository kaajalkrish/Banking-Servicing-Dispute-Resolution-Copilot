"""Tests for the trace-export coverage verifier (§7.2 Trace export)."""

from __future__ import annotations

import pandas as pd

import scripts.verify_trace_export as v


def test_multi_agent_coverage_ok_with_supervisor_and_workers():
    assert v.check_multi_agent_coverage({"supervisor", "account_servicing", "dispute", "product_info"}) == []


def test_multi_agent_coverage_fails_without_supervisor():
    problems = v.check_multi_agent_coverage({"account_servicing", "dispute", "product_info"})
    assert any("supervisor" in p for p in problems)


def test_multi_agent_coverage_fails_with_too_few_workers():
    problems = v.check_multi_agent_coverage({"supervisor", "account_servicing"})
    assert any("worker" in p for p in problems)


def test_tool_call_coverage_ok_when_all_logged_tools_have_spans():
    assert v.check_tool_call_coverage({"get_account_balance", "create_dispute_case"}, {"get_account_balance"}) == []


def test_tool_call_coverage_flags_missing_span():
    problems = v.check_tool_call_coverage({"get_account_balance"}, {"get_account_balance", "policy_search"})
    assert len(problems) == 1 and "policy_search" in problems[0]


def test_latencies_present_ok():
    df = pd.DataFrame({"start_time": [1, 2], "end_time": [3, 4]})
    assert v.check_latencies_present(df) == []


def test_latencies_present_flags_nulls():
    df = pd.DataFrame({"start_time": [1, None], "end_time": [3, 4]})
    assert len(v.check_latencies_present(df)) == 1


def test_run_id_present_handles_dict_form():
    """A raw dataframe fresh off the Phoenix client has dict-valued metadata."""
    df = pd.DataFrame({"attributes.metadata": [{"run_id": "run-1"}, None]})
    assert v.check_run_id_present(df) == []


def test_run_id_present_handles_json_stringified_form():
    """A committed parquet has metadata JSON-stringified by export.py's
    _stringify_nested_columns() -- this is the real, committed shape."""
    df = pd.DataFrame({"attributes.metadata": ['{"run_id": "run-1"}', None]})
    assert v.check_run_id_present(df) == []


def test_run_id_present_flags_when_absent_in_either_form():
    df = pd.DataFrame({"attributes.metadata": [{"foo": "bar"}, '{"baz": 1}']})
    assert len(v.check_run_id_present(df)) == 1
