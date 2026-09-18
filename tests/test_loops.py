"""Loop / cascade guard tests (§7.6, NFR-04, §8 Agent tests).

Asserts that:
1. A deliberately looping graph (supervisor keeps routing to a worker that never
   produces a result) is stopped by the max-steps guard and ends in escalation,
   gracefully — not with an unhandled recursion error.
2. A failing tool does not cause a retry storm: non-transient errors are tried
   once and transient errors are retried a bounded number of times.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from src.agents.escalate import escalate_node
from src.agents.supervisor import route_from_supervisor, supervisor_node
from src.graph import finalize_node, run_config
from src.state import CopilotState, new_state
from src.tools.resilience import resilient_ainvoke
from tests._fakes import FakeSupervisorLLM


def _looping_graph(max_route_to: str = "account_servicing"):
    """A graph whose worker never records a result, so the supervisor would loop
    forever without the step guard."""

    async def noop_worker(_state):
        return {}  # deliberately records nothing

    g = StateGraph(CopilotState)
    g.add_node("supervisor", partial(supervisor_node, llm=FakeSupervisorLLM(max_route_to)))
    g.add_node("account_servicing", noop_worker)
    g.add_node("escalate_human", escalate_node)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "intake": "account_servicing",
            "account_servicing": "account_servicing",
            "dispute": "account_servicing",
            "product_info": "account_servicing",
            "escalate_human": "escalate_human",
            "finalize": "finalize",
        },
    )
    g.add_edge("account_servicing", "supervisor")
    g.add_edge("escalate_human", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


async def test_max_steps_guard_stops_loop_and_escalates():
    g = _looping_graph()
    state = new_state("C0001", "loop forever please", max_steps=3)
    # recursion_limit is generous; the max-steps guard must fire first.
    out = await g.ainvoke(state, {"recursion_limit": 50})
    assert out["escalated"] is True
    assert out["final_answer"]["requires_human_review"] is True
    assert out["step_count"] > out["max_steps"]


def test_run_config_sets_recursion_limit():
    cfg = run_config("T1")
    assert cfg["recursion_limit"] >= 1
    assert cfg["configurable"]["thread_id"] == "T1"


async def test_failing_tool_does_not_retry_storm():
    class NonTransientTool:
        name = "boom"

        def __init__(self):
            self.calls = 0

        async def ainvoke(self, _args):
            self.calls += 1
            raise RuntimeError("hard failure")

    t = NonTransientTool()
    res = await resilient_ainvoke(t, {}, retries=3)
    assert res["ok"] is False
    assert t.calls == 1  # non-transient: tried once, no retry storm


async def test_transient_tool_retries_are_bounded():
    class TransientTool:
        name = "rate"

        def __init__(self):
            self.calls = 0

        async def ainvoke(self, _args):
            self.calls += 1
            raise RuntimeError("429 rate limit exceeded")

    t = TransientTool()
    res = await resilient_ainvoke(t, {}, retries=2, timeout=1.0)
    assert res["ok"] is False
    assert t.calls == 3  # initial + exactly 2 retries, then gives up
