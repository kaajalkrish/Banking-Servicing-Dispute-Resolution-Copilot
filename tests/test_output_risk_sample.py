"""Tests for scripts/output_risk_sample.py (ref-doc.md §7.5 sample; NFR-06).

Offline and model-free: the script only joins committed evidence.
"""

from __future__ import annotations

import json

import scripts.output_risk_sample as s


def _final(run_id: str, worker: str, tier: str, review: bool) -> dict:
    return {
        "run_id": run_id,
        "actor": "finalize",
        "action": "finalize_answer",
        "decision": tier,
        "reason_code": worker,
        "details": {"requires_human_review": review},
    }


def _case(case_id: str, run_ids: list[str], answer: str = "an answer", category: str = "cat") -> dict:
    return {"id": case_id, "category": category, "run_ids": run_ids, "actual_output": answer}


_AUDIT = [
    _final("r1", "account_servicing", "medium", False),
    _final("r2", "product_info", "low", False),
    _final("r3", "dispute", "high", True),
    _final("r4", "product_info", "low", True),
    {"run_id": "r3", "actor": "output_guard", "action": "sanitize_output", "decision": "sanitized"},
]
_EVAL = {
    "results": [
        _case("a", ["r1"]),
        _case("b", ["r2"]),
        _case("c", ["x0", "r3"]),  # multi-turn: the last run_id is the one whose answer was recorded
        _case("d", ["r4"]),
    ]
}


def test_gate_decision_wording():
    assert s.gate_decision("high", True).startswith("gated: human review")
    assert s.gate_decision("high", False).startswith("gated: human review")  # high is always gated
    assert s.gate_decision("low", True).startswith("flagged for human review")
    assert s.gate_decision("medium", False) == "released to the customer"


def test_cases_are_joined_to_their_audit_records_by_run_id():
    sample = s.build_sample(_EVAL, _AUDIT)
    assert sample["eval_linked_cases"] == 4
    by_case = {e["case_id"]: e for tier in sample["examples"].values() for e in tier}
    assert by_case["c"]["run_id"] == "r3"  # last turn of a multi-turn case
    assert by_case["c"]["tier"] == "high" and by_case["c"]["worker"] == "dispute"
    assert by_case["c"]["guard_actions"] == ["output_guard:sanitize_output"]
    assert by_case["a"]["gate"] == "released to the customer"


def test_totals_cover_every_audit_record_not_only_linked_ones():
    audit = [*_AUDIT, _final("orphan", "escalate_human", "high", True)]
    totals = s.build_sample(_EVAL, audit)["audit_trail_totals"]
    assert totals["finalize_records"] == 5
    assert totals["by_tier"] == {"low": 2, "medium": 1, "high": 2}
    assert totals["by_tier_and_review_flag"]["low/human_review=True"] == 1


def test_examples_are_capped_per_tier_and_worker_and_deterministic():
    audit = [_final(f"r{i}", "product_info", "low", False) for i in range(5)]
    evaluation = {"results": [_case(f"c{i}", [f"r{i}"]) for i in reversed(range(5))]}
    sample = s.build_sample(evaluation, audit)
    assert [e["case_id"] for e in sample["examples"]["low"]] == ["c0", "c1"]  # sorted by case id, capped at 2


def test_answer_excerpts_are_masked_and_truncated():
    audit = [_final("r1", "account_servicing", "medium", False)]
    evaluation = {"results": [_case("a", ["r1"], answer="Card 4111111111111111 " + "x" * 500)]}
    excerpt = s.build_sample(evaluation, audit)["examples"]["medium"][0]["answer_excerpt"]
    assert "4111111111111111" not in excerpt
    assert len(excerpt) <= s.EXCERPT_CHARS


def test_a_tier_that_disagrees_with_the_classifier_is_reported():
    bad = [_final("r1", "dispute", "low", False)]  # a dispute answer can never be low-risk
    integrity = s.build_sample({"results": [_case("a", ["r1"])]}, bad)["integrity"]
    assert integrity["logged_tier_matches_classifier"] is False
    assert integrity["mismatched_run_ids"] == ["r1"]


def test_input_guard_refusals_are_low_tier_but_flagged_for_review():
    audit = [_final("r1", "input_guard", "low", True)]
    sample = s.build_sample({"results": [_case("a", ["r1"])]}, audit)
    assert sample["integrity"]["logged_tier_matches_classifier"] is True
    assert sample["examples"]["low"][0]["gate"].startswith("flagged for human review")


def test_cases_without_an_audit_record_are_skipped():
    sample = s.build_sample({"results": [_case("a", ["missing"]), _case("b", [])]}, _AUDIT)
    assert sample["eval_linked_cases"] == 0


def test_main_writes_the_report_and_fails_when_nothing_links(tmp_path, capsys):
    (tmp_path / "eval.json").write_text(json.dumps(_EVAL), encoding="utf-8")
    (tmp_path / "audit.jsonl").write_text("\n".join(json.dumps(a) for a in _AUDIT), encoding="utf-8")
    out = tmp_path / "out.json"
    argv = ["--eval", str(tmp_path / "eval.json"), "--audit", str(tmp_path / "audit.jsonl"), "--out", str(out)]
    assert s.main(argv) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert set(written["sources"]) == {str(tmp_path / "eval.json"), str(tmp_path / "audit.jsonl")}
    assert "generated_at" in written

    (tmp_path / "eval.json").write_text(json.dumps({"results": [_case("z", ["nope"])]}), encoding="utf-8")
    assert s.main(argv) == 1
    assert "FAIL" in capsys.readouterr().err


def test_a_recursion_fallback_answer_is_excluded_not_paired_with_a_discarded_tier():
    from src.cli import recursion_fallback_state

    fallback = recursion_fallback_state()["final_answer"]["answer"]
    evaluation = {"results": [_case("a", ["r1"]), _case("b", ["r2"], answer=fallback)]}
    sample = s.build_sample(evaluation, _AUDIT)
    assert sample["eval_linked_cases"] == 1
    assert sample["excluded_cases"] == [{"case_id": "b", "reason": s.EXCLUDED_REASON}]
    listed = {e["case_id"] for tier in sample["examples"].values() for e in tier}
    assert listed == {"a"}
