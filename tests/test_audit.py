"""Tests for the audit middleware (AC-10, §7.4 Audit trail)."""

from __future__ import annotations

import json

from src.common.ids import bind_run_id
from src.guardrails.audit import hash_customer_ref, record_action

REQUIRED_FIELDS = {
    "timestamp", "run_id", "actor", "action", "tool", "decision",
    "reason_code", "customer_ref", "details",
}


def _read_records(log_dir) -> list[dict]:
    path = log_dir / "agent_actions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_record_action_writes_all_required_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    with bind_run_id("run-audit-1"):
        record_action(
            actor="dispute", action="create_dispute", decision="drafted",
            tool="create_dispute_case", reason_code="eligible", customer_id="C0001",
            details={"transaction_id": "TXN0000001"},
        )
    records = _read_records(tmp_path)
    assert len(records) == 1
    assert REQUIRED_FIELDS <= set(records[0])
    assert records[0]["run_id"] == "run-audit-1"


async def test_customer_ref_is_hashed_not_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    record_action(actor="gateway", action="tool_call", decision="denied", customer_id="C0001")
    records = _read_records(tmp_path)
    assert records[0]["customer_ref"] == hash_customer_ref("C0001")
    blob = (tmp_path / "agent_actions.jsonl").read_text(encoding="utf-8")
    assert "C0001" not in blob


async def test_pan_in_details_is_masked(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    record_action(
        actor="dispute", action="create_dispute", decision="drafted",
        details={"card_number": "4111111111111111"},
    )
    blob = (tmp_path / "agent_actions.jsonl").read_text(encoding="utf-8")
    assert "4111111111111111" not in blob


async def test_no_run_id_scope_records_none(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    record_action(actor="dispute", action="create_dispute", decision="drafted")
    records = _read_records(tmp_path)
    assert records[0]["run_id"] is None


async def test_record_action_never_raises_on_write_failure(tmp_path, monkeypatch):
    """LOG_DIR pointing at a path that collides with an existing FILE (so
    mkdir must fail) must not propagate an exception — audit logging is
    best-effort and must never break the calling code."""
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LOG_DIR", str(blocking_file / "logs"))  # can't mkdir under a file
    record_action(actor="dispute", action="create_dispute", decision="drafted")  # must not raise
