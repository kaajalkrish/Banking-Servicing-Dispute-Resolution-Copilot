"""Tests for the dispute worker's optimization-profile switch (P5-13, §8.1).

The `optimized` profile (default) runs check_dispute_eligibility, policy_search
and create_dispute_case concurrently via asyncio.gather, since none of their
arguments depend on another call's result. The `baseline` profile keeps the
original sequential order, so the §8.1 before/after comparison has real,
unmodified code to compare against. Both profiles must produce byte-identical
final output for the same tool results -- the optimization changes only call
ordering/timing, never behaviour.
"""

from __future__ import annotations

import asyncio
import time
import types
from typing import Any

import src.agents.dispute as dispute_module
from src.agents.dispute import dispute_node
from src.context.quarantine import ExtractedDisputeFields
from src.state import new_state
from tests._fakes import FakeWorkerLLM


class _TimedTool:
    """A fake tool that records when it started/finished and sleeps for
    `delay` seconds, so concurrency can be measured empirically rather than
    just asserted from the code shape."""

    def __init__(self, name: str, result: Any, *, delay: float, log: list[tuple[str, float, float]]) -> None:
        self.name = name
        self._result = result
        self._delay = delay
        self._log = log

    async def ainvoke(self, _args: Any) -> Any:
        start = time.perf_counter()
        await asyncio.sleep(self._delay)
        end = time.perf_counter()
        self._log.append((self.name, start, end))
        return self._result


def _tools(delay: float, log: list[tuple[str, float, float]]) -> list[Any]:
    return [
        _TimedTool(
            "check_dispute_eligibility",
            {"eligible": True, "window_days": 60, "days_since_transaction": 5, "explanation": ["within window"]},
            delay=delay,
            log=log,
        ),
        _TimedTool(
            "policy_search",
            {"answer": "Fee information.", "citations": [{"doc_id": "POL-FEES", "section": "Overdraft Fee"}], "abstained": False},
            delay=delay,
            log=log,
        ),
        _TimedTool("create_dispute_case", {"dispute_id": "DSP00001", "status": "draft"}, delay=delay, log=log),
    ]


def _worker_llm() -> FakeWorkerLLM:
    return FakeWorkerLLM(
        "Your dispute has been drafted for human review.",
        structured_result=ExtractedDisputeFields(transaction_id="TXN0001234", reason_hint="unrecognized_charge"),
    )


async def _run(monkeypatch, profile: str, delay: float, log: list[tuple[str, float, float]]) -> tuple[dict, float]:
    monkeypatch.setattr(dispute_module, "settings", types.SimpleNamespace(optimization_profile=profile))
    state = new_state("C0001", "Dispute TXN0001234 for an unrecognized charge.", max_steps=12)
    start = time.perf_counter()
    update = await dispute_node(state, tools=_tools(delay, log), llm=_worker_llm())
    elapsed = time.perf_counter() - start
    return update, elapsed


async def test_optimized_profile_runs_the_three_tool_calls_concurrently(monkeypatch):
    log: list[tuple[str, float, float]] = []
    _update, elapsed = await _run(monkeypatch, "optimized", delay=0.05, log=log)
    assert len(log) == 3
    # Concurrent: total wall-clock is close to ONE delay, not three.
    assert elapsed < 0.05 * 2.5, f"expected concurrent execution (~0.05s), took {elapsed:.3f}s"
    # Overlap check: the latest-starting call must have started before the
    # earliest-finishing call finished -- proof that at least two calls were
    # in flight at the same moment.
    starts = [s for _, s, _ in log]
    ends = [e for _, _, e in log]
    assert max(starts) < min(ends), "no overlap detected between the three calls"


async def test_baseline_profile_runs_the_three_tool_calls_sequentially(monkeypatch):
    log: list[tuple[str, float, float]] = []
    _update, elapsed = await _run(monkeypatch, "baseline", delay=0.05, log=log)
    assert len(log) == 3
    # Sequential: total wall-clock is close to THREE delays, not one.
    assert elapsed > 0.05 * 2.5, f"expected sequential execution (~0.15s), took {elapsed:.3f}s"
    # No two calls overlap: each one's start is at/after the previous one's end.
    ordered = sorted(log, key=lambda row: row[1])
    for (_, _s1, e1), (_, s2, _e2) in zip(ordered, ordered[1:]):
        assert s2 >= e1 - 0.005, "sequential calls overlapped"


async def test_optimized_and_baseline_produce_identical_final_output(monkeypatch):
    log_a: list[tuple[str, float, float]] = []
    log_b: list[tuple[str, float, float]] = []
    update_optimized, _ = await _run(monkeypatch, "optimized", delay=0.0, log=log_a)
    update_baseline, _ = await _run(monkeypatch, "baseline", delay=0.0, log=log_b)
    assert update_optimized == update_baseline


async def test_optimized_profile_is_the_default(monkeypatch):
    # No monkeypatch of settings at all -- the real src.config.settings
    # singleton must default optimization_profile to "optimized".
    from src.config import settings

    assert settings.optimization_profile == "optimized"
