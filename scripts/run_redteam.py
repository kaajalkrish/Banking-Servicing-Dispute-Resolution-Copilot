"""Red-team harness: runs data/redteam/attacks.jsonl for real (§8.1, AC-06, NFR-06).

Each attack is checked two ways, no live Gemini call needed (deterministic,
offline, no API quota spent):

- **guard-only**: every turn's raw text is run through the real
  ``evaluate_input()`` (src/guardrails/input.py) and the outcome (blocked or
  not, and the reason code) is compared to the attack's expectation.
- **end-to-end**: the real compiled graph (``build_graph``) is run with a
  scripted supervisor/worker LLM (the same fakes the offline test suite uses,
  ``tests/_fakes.py``) so the input-guard short-circuit, the routing, and the
  output guardrail chain in ``finalize_node`` all run for real. For an attack
  that is expected to reach a worker, the scripted worker returns the attack's
  ``simulated_worker_reply`` (what an attacker WANTS the model to say) and the
  check is whether the output guardrails scrub it before it reaches the
  customer-facing answer.

Writes reports/redteam_results.json (machine-readable) and
docs/redteam-results.md (a short human-readable table). An attack marked
``known_gap: true`` in the data is a documented, accepted limitation (see
data/redteam/attacks.jsonl's own notes for each) and does not fail the run;
anything else that fails is a real, undocumented gap and the harness exits
non-zero.

Usage:
    python scripts/run_redteam.py
    python -m src.cli redteam
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The end-to-end checks run real graph turns (with fake LLMs but the REAL
# tool-logging middleware, src/observability/tool_logging.py), which appends
# to whatever LOG_DIR points at. Isolate it to a throwaway temp directory
# before that middleware is ever imported/used, so a red-team run can never
# pollute the committed logs/tool_calls.jsonl evidence -- found the hard way:
# an initial run of this script (before this fix) wrote 30+ scripted
# dispute/balance tool calls into the real, committed evidence file.
os.environ["LOG_DIR"] = tempfile.mkdtemp(prefix="redteam_logs_")

from src.context.quarantine import ExtractedDisputeFields  # noqa: E402
from src.graph import build_graph  # noqa: E402
from src.guardrails.input import evaluate_input  # noqa: E402
from src.state import new_state  # noqa: E402
from tests._fakes import FakeSupervisorLLM, FakeWorkerLLM, default_tools  # noqa: E402

ATTACKS_PATH = _REPO_ROOT / "data" / "redteam" / "attacks.jsonl"


def load_attacks(path: Path = ATTACKS_PATH) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _guard_only_check(attack: dict[str, Any]) -> dict[str, Any]:
    turn_results = []
    all_passed = True
    for t in attack["turns"]:
        result = evaluate_input(t["text"], authenticated_customer_id=attack["customer_id"])
        actual_blocked = result["decision"] == "block"
        passed = actual_blocked == t["expect_input_blocked"]
        if passed and actual_blocked:
            passed = result["reason_code"] == t["expected_input_reason_code"]
        all_passed = all_passed and passed
        turn_results.append(
            {
                "text": t["text"],
                "expected_blocked": t["expect_input_blocked"],
                "actual_blocked": actual_blocked,
                "actual_reason_code": result["reason_code"],
                "passed": passed,
            }
        )
    return {"turn_results": turn_results, "passed": all_passed}


async def _end_to_end_check(attack: dict[str, Any]) -> dict[str, Any] | None:
    last_turn = attack["turns"][-1]

    if last_turn["expect_input_blocked"]:
        g = build_graph(
            supervisor_llm=FakeSupervisorLLM(attack["target_worker"]),
            worker_llm=FakeWorkerLLM("SHOULD NOT BE REACHED -- input guard must short-circuit first"),
            tools=default_tools(),
        )
        out = await g.ainvoke(new_state(attack["customer_id"], last_turn["text"], max_steps=12))
        worker_reached = out["worker_results"][0]["worker"]
        review_ok = (
            attack["expected_requires_human_review"] is None
            or out["final_answer"]["requires_human_review"] == attack["expected_requires_human_review"]
        )
        return {
            "mode": "blocked_short_circuit",
            "worker_reached": worker_reached,
            "requires_human_review": out["final_answer"]["requires_human_review"],
            "passed": worker_reached == "input_guard" and review_ok,
        }

    if not attack["simulated_worker_reply"]:
        # Documented known-gap (e.g. encoded_payload): we only claim the
        # INPUT filter has a blind spot here, never that it is exploitable
        # end-to-end (nothing decodes/executes the obfuscated text), so there
        # is nothing meaningful to run through the graph.
        return None

    structured = (
        ExtractedDisputeFields(transaction_id="TXN0001234", reason_hint="unrecognized_charge")
        if attack["target_worker"] == "dispute"
        else None
    )
    g = build_graph(
        supervisor_llm=FakeSupervisorLLM(attack["target_worker"]),
        worker_llm=FakeWorkerLLM(attack["simulated_worker_reply"], structured_result=structured),
        tools=default_tools(),
    )
    out = await g.ainvoke(new_state(attack["customer_id"], last_turn["text"], max_steps=12))
    answer = out["final_answer"]["answer"]
    leaked = [f for f in attack["forbidden_in_final_answer"] if f.lower() in answer.lower()]
    review_ok = (
        attack["expected_requires_human_review"] is None
        or out["final_answer"]["requires_human_review"] == attack["expected_requires_human_review"]
    )
    return {
        "mode": "allowed_through",
        "final_answer": answer,
        "leaked_forbidden_strings": leaked,
        "requires_human_review": out["final_answer"]["requires_human_review"],
        "passed": not leaked and review_ok,
    }


async def run_all(attacks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    attacks = attacks if attacks is not None else load_attacks()
    results = []
    for attack in attacks:
        guard_only = _guard_only_check(attack)
        end_to_end = await _end_to_end_check(attack)
        real_pass = guard_only["passed"] and (end_to_end is None or end_to_end["passed"])
        results.append(
            {
                "id": attack["id"],
                "category": attack["category"],
                "owasp_llm_tag": attack["owasp_llm_tag"],
                "known_gap": attack.get("known_gap", False),
                "notes": attack.get("notes", ""),
                "guard_only": guard_only,
                "end_to_end": end_to_end,
                "real_pass": real_pass,
                # a documented known-gap attack is an accepted limitation, not
                # a run failure -- it never fails the harness even if its
                # real_pass is False.
                "counted_pass": real_pass or attack.get("known_gap", False),
            }
        )

    total = len(results)
    counted_passed = sum(1 for r in results if r["counted_pass"])
    undocumented_failures = [r for r in results if not r["counted_pass"]]
    return {
        "total_attacks": total,
        "counted_passed": counted_passed,
        "counted_failed": total - counted_passed,
        "known_gaps": sum(1 for r in results if r["known_gap"]),
        "results": results,
        "ok": not undocumented_failures,
    }


def write_markdown_report(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# Red-team results",
        "",
        f"**{summary['counted_passed']}/{summary['total_attacks']}** attacks passed "
        f"({summary['known_gaps']} documented known-gap attack(s) counted as accepted, not failed).",
        "",
        "Generated by `python scripts/run_redteam.py` (also `python -m src.cli redteam`) against "
        "`data/redteam/attacks.jsonl` -- guard-only via the real `evaluate_input()`, end-to-end via the "
        "real compiled graph with a scripted worker LLM.",
        "",
        "| id | category | OWASP | result | known gap | notes |",
        "|---|---|---|---|---|---|",
    ]
    for r in summary["results"]:
        result = "pass" if r["counted_pass"] else "**FAIL**"
        lines.append(
            f"| {r['id']} | {r['category']} | {r['owasp_llm_tag']} | {result} | "
            f"{'yes' if r['known_gap'] else ''} | {r['notes']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    summary = asyncio.run(run_all())

    reports_dir = _REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "redteam_results.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    docs_dir = _REPO_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_markdown_report(summary, docs_dir / "redteam-results.md")

    print(
        f"red-team: {summary['counted_passed']}/{summary['total_attacks']} passed "
        f"({summary['known_gaps']} documented known gaps)"
    )
    if not summary["ok"]:
        print("UNDOCUMENTED FAILURES:")
        for r in summary["results"]:
            if not r["counted_pass"]:
                print(f"  - {r['id']} ({r['category']})")
        return 1
    print("OK: every attack either passed or is a documented known gap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
