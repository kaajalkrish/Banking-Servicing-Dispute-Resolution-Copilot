"""Evaluation harness (ref-doc.md §7.6 Evaluation report, AC-12).

Runs every case in data/golden_set/golden.jsonl through the real, traced,
guarded graph (the same one the CLI drives), scores it with DeepEval
(hallucination, faithfulness, answer relevancy, all judged by Gemini via
GeminiJudge) plus a custom "accuracy" metric that compares the graph's
*observed* behavior classification against the golden case's
expected_behavior label, and writes reports/eval_report.json.

Observed-behavior classification is read from real state/code signals, not
regexed off the answer text:
  - the input-guard's block path is the ONLY place that appends a
    worker_results entry with worker == "input_guard" (src/graph.py
    ingress_input_guard_node) -> "refuse"
  - product_info's only requires_human_review trigger is RAG abstention
    (src/agents/product_info.py) -> "abstain"
  - anything else left with requires_human_review / escalated set (dispute
    always does, per D-13; escalate_human always does; a hard
    GraphRecursionError degrade always does) -> "escalate"
  - otherwise -> "answer" (this also covers intake's clarifying question,
    which is the correct AC-04 behavior and not a human handoff)
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from src.common.ids import new_run_id
from src.common.masking import mask_obj
from src.config import settings

GOLDEN_SET_PATH = Path("data/golden_set/golden.jsonl")
DEFAULT_OUT_PATH = Path("reports/eval_report.json")
POLICY_CORPUS_DIR = Path("data/policy_corpus")

_PACKAGES = ("deepeval", "langgraph", "langchain-google-genai")


def _package_versions() -> dict[str, str]:
    out = {}
    for pkg in _PACKAGES:
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "unknown"
    return out


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - metadata only, never fatal
        return "unknown"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_golden_set(path: Path = GOLDEN_SET_PATH, *, limit: int | None = None) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return cases[:limit] if limit else cases


def classify_observed_behavior(out: dict[str, Any]) -> str:
    """Map one turn's graph output state to answer/abstain/refuse/escalate."""
    results = out.get("worker_results") or []
    last = results[-1] if results else {}
    if last.get("worker") == "input_guard":
        return "refuse"
    if last.get("worker") == "product_info" and last.get("requires_human_review"):
        return "abstain"
    fa = out.get("final_answer") or {}
    if fa.get("requires_human_review") or fa.get("escalated") or out.get("requires_human_review"):
        return "escalate"
    return "answer"


def _retrieval_context_from_citations(citations: list[dict[str, Any]]) -> list[str]:
    """Prefer the chunk text rag_tool.py attaches to raw worker_results
    citations (present pre-FinalAnswer validation, which strips it — see
    src/tools/rag_tool.py). Falls back to re-reading the corpus section by
    heading if an older citation shape without "text" is ever encountered."""
    texts: list[str] = []
    for c in citations:
        if c.get("text"):
            texts.append(f"[{c['doc_id']} §{c.get('section')}] {c['text']}")
            continue
        section = c.get("section")
        doc_id = c.get("doc_id", "")
        found = None
        if section:
            for fp in POLICY_CORPUS_DIR.glob("*.md"):
                body = fp.read_text(encoding="utf-8")
                if f"doc_id: {doc_id}" not in body:
                    continue
                m = re.search(rf"^## {re.escape(section)}\n(.+?)(?=\n## |\Z)", body, re.S | re.M)
                if m:
                    found = m.group(1).strip()
                break
        if found:
            texts.append(f"[{doc_id} §{section}] {found}")
    return texts


async def _run_case(graph: Any, case: dict[str, Any]) -> dict[str, Any]:
    from src.state import new_state
    from src.observability.tracing import traced_run

    from src.cli import _invoke_turn  # reuse the recursion-guard degrade path

    thread_id = f"eval-{case['id']}"
    out: dict[str, Any] = {}
    run_ids: list[str] = []
    for text in case["turns"]:
        run_id = new_run_id()
        run_ids.append(run_id)
        with traced_run(run_id):
            out = await _invoke_turn(
                graph,
                new_state(case["customer_id"], text, max_steps=settings.max_steps),
                {"configurable": {"thread_id": thread_id}},
            )

    fa = out.get("final_answer") or {}
    actual_output = fa.get("answer", "")
    worker_results = out.get("worker_results") or []
    context = [r["content"] for r in worker_results if r.get("content")]
    citations = worker_results[-1].get("citations", []) if worker_results else []
    retrieval_context = _retrieval_context_from_citations(citations)
    observed_behavior = classify_observed_behavior(out)

    return {
        "id": case["id"],
        "category": case["category"],
        "customer_id": case["customer_id"],
        "input": case["turns"][-1],
        "actual_output": actual_output,
        "context": context or None,
        "retrieval_context": retrieval_context or None,
        "expected_behavior": case["expected_behavior"],
        "observed_behavior": observed_behavior,
        "accuracy_match": observed_behavior == case["expected_behavior"],
        "run_ids": run_ids,
        "tags": case.get("tags", []),
    }


async def _score_case(judge: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Attach DeepEval metric scores to one already-run case result.

    Hallucination/Faithfulness need a context to check groundedness against;
    a refused/escalated/ambiguous-clarification turn often has none (nothing
    was retrieved or looked up), so those two are left null rather than
    scored against an empty context, which would only add noise. Answer
    relevancy is meaningful even for a refusal (does the reply actually
    address the input?), so it always runs.
    """
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, HallucinationMetric
    from deepeval.test_case import LLMTestCase

    tc = LLMTestCase(
        input=result["input"],
        actual_output=result["actual_output"] or "(empty)",
        context=result["context"],
        retrieval_context=result["retrieval_context"],
    )

    relevancy = AnswerRelevancyMetric(model=judge, include_reason=True, async_mode=False)
    await relevancy.a_measure(tc)
    result["answer_relevancy_score"] = relevancy.score
    result["answer_relevancy_reason"] = relevancy.reason

    ctx = result["retrieval_context"] or result["context"]
    if ctx:
        hallucination = HallucinationMetric(model=judge, include_reason=True, async_mode=False)
        tc_h = LLMTestCase(input=result["input"], actual_output=tc.actual_output, context=ctx)
        await hallucination.a_measure(tc_h)
        result["hallucination_score"] = hallucination.score
        result["hallucination_reason"] = hallucination.reason

        faithfulness = FaithfulnessMetric(model=judge, include_reason=True, async_mode=False)
        tc_f = LLMTestCase(
            input=result["input"], actual_output=tc.actual_output, retrieval_context=ctx
        )
        await faithfulness.a_measure(tc_f)
        result["faithfulness_score"] = faithfulness.score
        result["faithfulness_reason"] = faithfulness.reason
    else:
        result["hallucination_score"] = None
        result["faithfulness_score"] = None
    return result


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    accuracy = sum(1 for r in results if r["accuracy_match"]) / n if n else 0.0

    hall = [r["hallucination_score"] for r in results if r["hallucination_score"] is not None]
    # deepeval's HallucinationMetric scores 1=no hallucination (pass), 0=hallucinated
    # (a breaking change in deepeval 4.x vs older versions — see P5-02 commit).
    # "hallucination_rate" is reported in the conventional sense: the fraction
    # of scored cases that DID hallucinate.
    hallucination_rate = (1 - sum(hall) / len(hall)) if hall else None

    faith = [r["faithfulness_score"] for r in results if r["faithfulness_score"] is not None]
    faithfulness_mean = sum(faith) / len(faith) if faith else None

    rel = [r["answer_relevancy_score"] for r in results if r.get("answer_relevancy_score") is not None]
    relevancy_mean = sum(rel) / len(rel) if rel else None

    by_category: dict[str, dict[str, float]] = {}
    for r in results:
        cat = r["category"]
        bucket = by_category.setdefault(cat, {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += int(r["accuracy_match"])
    pass_rate_by_category = {
        cat: (v["correct"] / v["n"] if v["n"] else 0.0) for cat, v in by_category.items()
    }

    return {
        "accuracy": accuracy,
        "hallucination_rate": hallucination_rate,
        "faithfulness_mean": faithfulness_mean,
        "answer_relevancy_mean": relevancy_mean,
        "pass_rate_by_category": pass_rate_by_category,
        "case_count": n,
        "scored_for_hallucination_faithfulness": len(hall),
    }


async def run_eval(
    *,
    golden_set_path: Path = GOLDEN_SET_PATH,
    out_path: Path = DEFAULT_OUT_PATH,
    limit: int | None = None,
    score: bool = True,
) -> dict[str, Any]:
    """Run the golden set through the live graph and (optionally) score it.

    score=False skips the DeepEval metric calls entirely (graph-only smoke
    test / faster accuracy-only check) -- useful given each metric call is
    its own Gemini request on top of the graph's own calls.
    """
    import time

    from src.evaluation.gemini_judge import GeminiJudge
    from src.graph import build_graph, open_checkpointer, run_config  # noqa: F401 (run_config unused; thread_id built inline)
    from src.llm import call_count, get_llm, reset_call_count
    from src.memory.long_term import build_extractor, open_memory_store
    from src.observability.tracing import flush_tracing, init_tracing
    from src.cli import _load_tools

    settings.require_api_key()
    init_tracing()

    cases = load_golden_set(golden_set_path, limit=limit)
    print(f"eval: {len(cases)} case(s) to run (scoring={'on' if score else 'off'})", flush=True)
    tools = await _load_tools()
    worker_llm = get_llm("default")
    judge = GeminiJudge() if score else None

    results: list[dict[str, Any]] = []
    async with open_checkpointer() as saver, open_memory_store() as mstore:
        graph = build_graph(
            supervisor_llm=get_llm("fast"),
            worker_llm=worker_llm,
            tools=tools,
            checkpointer=saver,
            memory_store=mstore,
            memory_extractor=build_extractor(worker_llm, mstore),
        )
        # Sequential, not gathered: cases run in file order so a
        # memory_return_visit_session2 case can rely on its session1 case
        # (earlier in the file) having already saved memory through the same
        # shared memory_store -- and it keeps Gemini call concurrency low,
        # which matters given the real per-minute rate limits hit in Phase 4.
        for i, case in enumerate(cases, 1):
            reset_call_count()
            t0 = time.monotonic()
            r = await _run_case(graph, case)
            if judge is not None:
                await _score_case(judge, r)
            else:
                r["hallucination_score"] = None
                r["faithfulness_score"] = None
                r["answer_relevancy_score"] = None
            elapsed = time.monotonic() - t0
            results.append(r)
            match = "OK" if r["accuracy_match"] else "MISMATCH"
            print(
                f"eval: [{i}/{len(cases)}] {case['id']} ({case['category']}) -- "
                f"{call_count()} calls, {elapsed:.1f}s, expected={case['expected_behavior']} "
                f"observed={r['observed_behavior']} [{match}]",
                flush=True,
            )
    flush_tracing()

    report = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": _git_commit(),
            "dataset_path": str(golden_set_path),
            "dataset_sha256": _sha256_file(golden_set_path),
            "worker_model": settings.gemini_model,
            "judge_model": settings.gemini_judge_model,
            "scored": score,
            "package_versions": _package_versions(),
        },
        "metrics": _aggregate(results),
        "results": results,
    }
    # Defense-in-depth (NFR-05): worker_results in raw graph state is not
    # itself re-sanitized by the output guardrail (only the final answer's
    # local copy is, inside finalize_node) -- in practice the underlying MCP
    # tool outputs are already masked at the source, but every committed
    # report/log in this project masks again at the point of writing rather
    # than trusting an upstream layer.
    masked_report = mask_obj(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(masked_report, indent=2, ensure_ascii=False), encoding="utf-8")
    return masked_report
