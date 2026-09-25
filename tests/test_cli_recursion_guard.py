"""Tests for _invoke_turn's graceful GraphRecursionError handling (NFR-04).

A real live run hit LangGraph's hard recursion_limit (see
notes/failures.local.md) — this asserts the CLI degrades to a safe, escalated
answer instead of letting the whole process (and, in a batch run, the rest of
the conversations) crash.
"""

from __future__ import annotations

from langgraph.errors import GraphRecursionError

from src.cli import _answer_for, _invoke_turn


class _RecursionLimitedGraph:
    async def ainvoke(self, state, config):
        raise GraphRecursionError("Recursion limit of 60 reached without hitting a stop condition.")


class _NormalGraph:
    async def ainvoke(self, state, config):
        return {"final_answer": {"answer": "all good", "requires_human_review": False}}


async def test_recursion_error_degrades_to_escalation_not_a_crash():
    out = await _invoke_turn(_RecursionLimitedGraph(), {}, {})
    assert out["final_answer"]["escalated"] is True
    assert out["final_answer"]["requires_human_review"] is True
    assert out["final_answer"]["risk_tier"] == "high"
    answer = await _answer_for(out)
    assert "human banking agent" in answer.lower()


async def test_normal_invocation_is_unaffected():
    out = await _invoke_turn(_NormalGraph(), {}, {})
    assert out["final_answer"]["answer"] == "all good"
