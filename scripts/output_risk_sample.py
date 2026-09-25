"""Output-risk sample from REAL runs (ref-doc.md §7.5 Output-risk classification,
"a sample"; NFR-06).

Builds ``reports/output_risk_sample.json`` with no model call: it joins the real
answers recorded in the evaluation report with the real output-risk decision the
audit trail logged for the same turn (``finalize_answer`` in
``logs/agent_actions.jsonl``), matched by ``run_id``. Nothing here is scripted or
hand-written.

Each example records the worker that produced the answer, the tier
(low / medium / high), whether the answer was gated to human review, and a
masked excerpt of the answer. A case whose recorded answer is the recursion-limit
fallback message is excluded and listed under ``excluded_cases``: its audit tier
belongs to an answer that was computed and then discarded (FA-03 in
docs/failure-analysis.md), so pairing the two would be misleading. The report also carries totals over every
finalize record in the audit trail, and an integrity check: the logged tier is
recomputed with the committed classifier (``classify_and_gate``) from the logged
worker and must match, otherwise the script exits non-zero.

Usage:
    python scripts/output_risk_sample.py [--eval PATH] [--audit PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.common.masking import mask_text  # noqa: E402
from src.guardrails.output_risk import classify_and_gate  # noqa: E402

EXAMPLES_PER_TIER_WORKER = 2
EXCERPT_CHARS = 240
TIERS = ("low", "medium", "high")
EXCLUDED_REASON = (
    "the recorded answer is the recursion-limit fallback, so the audit tier belongs to a "
    "different, discarded answer (FA-03)"
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate_decision(tier: str, requires_human_review: bool) -> str:
    """Plain-language gate outcome for a logged (tier, review flag) pair."""
    if tier == "high":
        return "gated: human review (high-risk tier is always gated)"
    if requires_human_review:
        return "flagged for human review (worker or guard requested it)"
    return "released to the customer"


def _finalize_by_run(audit: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The last ``finalize_answer`` record per run_id."""
    out: dict[str, dict[str, Any]] = {}
    for rec in audit:
        if rec.get("action") == "finalize_answer" and rec.get("run_id"):
            out[rec["run_id"]] = rec
    return out


def _guard_actions_by_run(audit: list[dict[str, Any]]) -> dict[str, list[str]]:
    actions: dict[str, list[str]] = {}
    for rec in audit:
        if rec.get("action") != "finalize_answer" and rec.get("run_id"):
            actions.setdefault(rec["run_id"], []).append(f"{rec.get('actor')}:{rec.get('action')}")
    return actions


def _consistent(record: dict[str, Any]) -> bool:
    """Recompute the tier with the committed classifier and compare."""
    worker = record.get("reason_code", "")
    review = bool((record.get("details") or {}).get("requires_human_review"))
    return classify_and_gate(worker, "", requires_human_review=review)["risk_tier"] == record.get("decision")


def build_sample(eval_report: dict[str, Any], audit: list[dict[str, Any]]) -> dict[str, Any]:
    finals = _finalize_by_run(audit)
    guards = _guard_actions_by_run(audit)

    from src.cli import recursion_fallback_state

    fallback_answer = recursion_fallback_state()["final_answer"]["answer"]
    linked: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for case in sorted(eval_report.get("results", []), key=lambda c: c["id"]):
        run_ids = case.get("run_ids") or []
        record = finals.get(run_ids[-1]) if run_ids else None  # the last turn's answer is the one recorded
        if record is None:
            continue
        if str(case.get("actual_output", "")).strip() == fallback_answer:
            excluded.append({"case_id": case["id"], "reason": EXCLUDED_REASON})
            continue
        review = bool((record.get("details") or {}).get("requires_human_review"))
        linked.append(
            {
                "case_id": case["id"],
                "category": case.get("category"),
                "run_id": run_ids[-1],
                "worker": record.get("reason_code"),
                "tier": record.get("decision"),
                "requires_human_review": review,
                "gate": gate_decision(record.get("decision", ""), review),
                "guard_actions": guards.get(run_ids[-1], []),
                "answer_excerpt": mask_text(str(case.get("actual_output", "")))[:EXCERPT_CHARS],
            }
        )

    examples: dict[str, list[dict[str, Any]]] = {t: [] for t in TIERS}
    seen: Counter[tuple[str, str]] = Counter()
    for item in linked:
        key = (item["tier"], item["worker"])
        if item["tier"] in examples and seen[key] < EXAMPLES_PER_TIER_WORKER:
            examples[item["tier"]].append(item)
            seen[key] += 1

    all_finals = list(finals.values())
    totals = Counter(rec.get("decision") for rec in all_finals)
    gates = Counter(
        (rec.get("decision"), bool((rec.get("details") or {}).get("requires_human_review"))) for rec in all_finals
    )
    inconsistent = [rec["run_id"] for rec in all_finals if not _consistent(rec)]

    return {
        "tier_rules": {
            "low": "cited policy information and clarifying questions (product_info, intake); also refusals from the input guard",
            "medium": "account-specific masked data (account_servicing)",
            "high": "dispute outcomes and any human escalation (dispute, escalate_human): always gated to human review",
            "source": "src/guardrails/output_risk.py (classify_and_gate)",
        },
        "audit_trail_totals": {
            "finalize_records": len(all_finals),
            "by_tier": {t: totals.get(t, 0) for t in TIERS},
            "by_tier_and_review_flag": {f"{t}/human_review={r}": n for (t, r), n in sorted(gates.items(), key=str)},
        },
        "eval_linked_cases": len(linked),
        "excluded_cases": excluded,
        "examples": examples,
        "integrity": {
            "logged_tier_matches_classifier": not inconsistent,
            "mismatched_run_ids": inconsistent,
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eval", default="reports/eval_report.json")
    p.add_argument("--audit", default="logs/agent_actions.jsonl")
    p.add_argument("--out", default="reports/output_risk_sample.json")
    args = p.parse_args(argv)

    eval_path, audit_path, out_path = Path(args.eval), Path(args.audit), Path(args.out)
    eval_report = json.loads(eval_path.read_text(encoding="utf-8"))
    audit = _read_jsonl(audit_path)

    sample = build_sample(eval_report, audit)
    sample["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sample["sources"] = {
        str(eval_path): _sha256(eval_path),
        str(audit_path): _sha256(audit_path),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    totals = sample["audit_trail_totals"]
    print(
        f"output-risk sample: {totals['finalize_records']} finalize records "
        f"{totals['by_tier']}; {sample['eval_linked_cases']} eval cases linked; wrote {out_path}"
    )
    if not sample["eval_linked_cases"] or not totals["finalize_records"]:
        print("FAIL: no eval case could be linked to an audit record", file=sys.stderr)
        return 1
    if not sample["integrity"]["logged_tier_matches_classifier"]:
        print(f"FAIL: logged tier disagrees with the classifier for {sample['integrity']['mismatched_run_ids']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
