"""Requirements-traceability suite: one test per requirement line in
`ref-doc.md` (the document `docs/plan.md` was itself built from), run for
real against the committed repository -- not a fake tmp_path repo like
`tests/test_verify_submission.py` (which tests the verifier's own logic).

Two layers:

1. Every check `scripts/verify_submission.py` runs is replayed here,
   parametrized so each one is its own pass/fail line in pytest's output
   (the §7 artifact rows, §6.2, and the §3.4 citation check), including
   `--check-git-merges` (§7.7 / NFR-07) -- known to fail today: `main`
   holds only the root commit, the six phase branches have not been
   merged in via pull request yet (see docs/delivery-runbook.md).
2. One hand-written test per acceptance criterion (AC-01..AC-12, §5.1) and
   non-functional requirement (NFR-01..NFR-07, §5.2) -- the narrative,
   behavioural requirements `verify_submission.py` does not check, each
   grounded in a specific piece of committed evidence (the same evidence
   `docs/check.md` cites, turned into a runnable assertion instead of
   prose). Plus one test for the one remaining §8.1 good-to-have item
   `verify_submission.py` never checked for at all (the optimization
   note), so a full run surfaces it instead of silently skipping it.

This file is not itself one of ref-doc.md's required artifacts -- it is an
internal QA tool, built on request, to give a single automated, repeatable
accuracy count and a concrete missing-items list against every requirement
line, rather than relying on the hand-written docs/check.md analysis alone.

Run:
    pytest tests/test_requirements_traceability.py -v
    pytest tests/test_requirements_traceability.py -v -k "not merges"   # skip the known NFR-07 gap
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.verify_submission as vs

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_json(rel: str) -> dict:
    return json.loads((_REPO_ROOT / rel).read_text(encoding="utf-8"))


def _read_jsonl(rel: str) -> list[dict]:
    path = _REPO_ROOT / rel
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_text(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# §7 artifact rows, §6.2, §3.4 citations -- every check verify_submission.py
# runs against the REAL committed repo, one per pytest id. Includes the git-
# merges check (§7.7 / NFR-07), known to fail until the PR merges are done.
# --------------------------------------------------------------------------- #

_SUBMISSION_CHECKS = vs.run_all(_REPO_ROOT, check_merges=True)


@pytest.mark.parametrize(
    "check", _SUBMISSION_CHECKS, ids=[f"{c.section}_{c.name}" for c in _SUBMISSION_CHECKS]
)
def test_submission_check(check: vs.Check) -> None:
    assert check.ok, check.detail


# --------------------------------------------------------------------------- #
# §5.1 Acceptance criteria AC-01 .. AC-12
# --------------------------------------------------------------------------- #

_EVAL = _read_json("reports/eval_report.json")


def _cases_tagged(ac: str) -> list[dict]:
    return [r for r in _EVAL["results"] if ac in r.get("tags", [])]


def test_ac01_account_info_grounded_in_tool_data() -> None:
    cases = _cases_tagged("AC-01")
    assert cases, "no golden-set case tagged AC-01"
    assert any(c["accuracy_match"] for c in cases), "no AC-01 case matched its expected behaviour"
    mcp = _read_jsonl("logs/mcp_transcript.jsonl")
    assert any(r.get("name") == "get_account_balance" for r in mcp), "no get_account_balance call in the MCP transcript"


def test_ac02_dispute_capture_eligibility_and_human_draft() -> None:
    cases = _cases_tagged("AC-02")
    assert cases, "no golden-set case tagged AC-02"
    assert any(c["accuracy_match"] for c in cases)
    assert (_REPO_ROOT / "src/agents/dispute.py").is_file()
    assert _read_json("reports/output_risk_sample.json"), "output-risk sample is empty"


def test_ac03_policy_answers_cited_and_abstains_when_unsupported() -> None:
    cases = _cases_tagged("AC-03")
    assert cases, "no golden-set case tagged AC-03"
    assert any(c["accuracy_match"] for c in cases)
    assert (_REPO_ROOT / "src/tools/rag_tool.py").is_file()


def test_ac04_intent_routed_ambiguous_or_out_of_scope_handled() -> None:
    cases = _cases_tagged("AC-04")
    assert cases, "no golden-set case tagged AC-04"
    assert "def test_" in _read_text("tests/test_routing.py")


def test_ac05_memory_recalls_across_sessions() -> None:
    log = _read_text("logs/memory_test.log")
    assert "PASS: cross-session recall verified with real Gemini + LangMem" in log


def test_ac06_injection_and_cross_customer_refused_pan_never_exposed() -> None:
    redteam = _read_json("reports/redteam_results.json")
    assert redteam["ok"], f"red-team has undocumented failures ({redteam['counted_failed']})"
    assert redteam["counted_passed"] == redteam["total_attacks"]
    pii = _read_json("reports/pii_scan.json")
    assert pii["ok"], f"unmasked PAN/account found in evidence: {pii['findings']}"


def test_ac07_tool_log_machine_generated_and_names_reconcile() -> None:
    calls = _read_jsonl("logs/tool_calls.jsonl")
    assert calls, "logs/tool_calls.jsonl has no records"
    required = {"timestamp", "agent", "tool_name", "args", "result", "latency_ms", "status"}
    assert all(required <= set(r) for r in calls)
    reconciliation = _read_json("reports/tool_reconciliation.json")
    assert reconciliation["ok"]
    assert not reconciliation["unknown_in_logs"]


def test_ac08_failure_analysis_has_three_real_failures_with_citations() -> None:
    doc = _read_text("docs/failure-analysis.md")
    fa_count = doc.count("\n## FA-")
    assert fa_count >= 3, f"only {fa_count} FA-xx entries in docs/failure-analysis.md"
    citations = _read_json("reports/citation_check.json")
    assert citations["ok"], citations["unresolved"]


def test_ac09_golden_signals_and_dashboard() -> None:
    gs = _read_json("reports/golden_signals.json")
    for cls in ("thinking", "acting", "tool"):
        assert "p50_ms" in gs["latency_by_class"][cls] and "p95_ms" in gs["latency_by_class"][cls]
    assert gs["tokens"]["input_tokens"] > 0 and gs["tokens"]["output_tokens"] > 0
    assert gs["cost"]["total_usd"] is not None
    assert gs["accuracy"] is not None and gs["hallucination_rate"] is not None
    assert (_REPO_ROOT / "reports/dashboard.png").is_file()
    assert (_REPO_ROOT / "reports/dashboard_data.csv").is_file()


def test_ac10_guardrails_wired_and_audit_trail_machine_generated() -> None:
    assert "input_guard" in _read_text("src/graph.py")
    actions = _read_jsonl("logs/agent_actions.jsonl")
    assert actions, "logs/agent_actions.jsonl has no records"
    required = {"actor", "action", "tool", "decision", "timestamp"}
    assert all(required <= set(a) for a in actions)


def test_ac11_governance_pack_citations_resolve() -> None:
    for doc in ("docs/risk-register.md", "docs/model-card.md", "docs/compliance.md", "docs/output-risk.md"):
        assert (_REPO_ROOT / doc).is_file() and (_REPO_ROOT / doc).stat().st_size > 0
    assert _read_json("reports/citation_check.json")["ok"]


def test_ac12_deepeval_report_and_agent_tests_exist() -> None:
    metrics = _EVAL["metrics"]
    for key in ("accuracy", "hallucination_rate", "faithfulness_mean", "answer_relevancy_mean"):
        assert metrics.get(key) is not None
    assert "gemini" in _EVAL["metadata"]["judge_model"].lower()
    for rel in ("tests/test_routing.py", "tests/test_loops.py", "tests/test_tool_contracts.py"):
        assert "def test_" in _read_text(rel)


# --------------------------------------------------------------------------- #
# §5.2 Non-functional requirements NFR-01 .. NFR-07
# --------------------------------------------------------------------------- #


def test_nfr01_no_secrets_committed() -> None:
    assert _read_json("reports/secrets_scan.json")["ok"]
    assert "GOOGLE_API_KEY" in _read_text(".env.example")
    assert ".env" in _read_text(".gitignore")


def test_nfr02_single_documented_run_and_regenerate_command() -> None:
    readme = _read_text("README.md")
    assert "python -m src.cli chat --customer-id" in readme
    assert "regenerate --traces --eval" in readme
    assert (_REPO_ROOT / "data/sample_inputs/conversations.jsonl").is_file()


def test_nfr03_untrusted_text_quarantined() -> None:
    quarantine = _read_text("src/context/quarantine.py")
    assert "QUARANTINE_OPEN" in quarantine and "QUARANTINE_CLOSE" in quarantine
    assert "quarantine" in _read_text("src/agents/dispute.py").lower()


def test_nfr04_async_resilience_and_loop_guards() -> None:
    assert "async def" in _read_text("src/graph.py")
    assert "timeout" in _read_text("src/tools/resilience.py").lower()
    llm = _read_text("src/llm.py").lower()
    assert "backoff" in llm or "retry" in llm
    for rel in ("tests/test_loops.py", "tests/test_cli_recursion_guard.py"):
        assert (_REPO_ROOT / rel).is_file()


def test_nfr05_synthetic_data_masked_never_plaintext() -> None:
    assert (_REPO_ROOT / "data/synthetic").is_dir()
    pii = _read_json("reports/pii_scan.json")
    assert pii["ok"], pii["findings"]


def test_nfr06_evidence_machine_generated_with_producing_code() -> None:
    manifest = _read_json("reports/evidence_manifest.json")
    assert manifest["ok"]
    assert manifest["artifact_count"] >= 20
    assert all(a.get("produced_by") for a in manifest["artifacts"])


def test_nfr07_pr_driven_git_history_no_direct_pushes_to_main() -> None:
    """Known, currently-failing gap: `main` holds only the root commit; the
    six phase branches are not yet merged in via pull request. See
    docs/delivery-runbook.md for the exact steps -- this cannot be closed
    from a local clone alone, it needs a real Git host."""
    check = next(c for c in _SUBMISSION_CHECKS if c.name.startswith("git merges"))
    assert check.ok, check.detail


# --------------------------------------------------------------------------- #
# §8.1 good-to-have items verify_submission.py does not check for at all
# --------------------------------------------------------------------------- #


def test_8_1_optimization_note_with_measured_before_after() -> None:
    """Good-to-have (§8.1, L219): a measured before/after latency or cost
    improvement, from two Phoenix-derived reports. Known, documented gap
    (docs/check.md, plan.md P5-11..15 deferred by team decision) -- included
    here so a full traceability run surfaces it as a missing item rather than
    silently skipping it (verify_submission.py has no check for it at all)."""
    candidates = (
        list(_REPO_ROOT.glob("reports/*baseline*"))
        + list(_REPO_ROOT.glob("reports/*optimi*"))
        + list(_REPO_ROOT.glob("docs/*optimi*"))
    )
    assert candidates, "no baseline/optimized before-after report found (section 8.1 good-to-have, deferred by team decision)"
