"""Routing-logic tests (§7.6, AC-04, §8 Agent tests).

Two layers, both offline:
1. Pure-function tests of route_from_supervisor over table-driven states.
2. Graph-level tests with a scripted fake supervisor LLM, asserting the right
   worker is selected — no network access.
"""

from __future__ import annotations

import pytest

from src.agents.supervisor import route_from_supervisor
from src.graph import build_graph
from src.state import new_state
from tests._fakes import FakeSupervisorLLM, FakeWorkerLLM, default_tools


@pytest.mark.parametrize(
    "route, expected",
    [
        ("account_servicing", "account_servicing"),
        ("dispute", "dispute"),
        ("product_info", "product_info"),
        ("intake", "intake"),
        ("escalate_human", "escalate_human"),
        ("finalize", "finalize"),
        ("", "escalate_human"),            # missing route -> safe default
        ("nonsense", "escalate_human"),    # invalid route -> safe default
    ],
)
def test_route_from_supervisor_table(route, expected):
    assert route_from_supervisor({"route": route}) == expected


@pytest.mark.parametrize(
    "worker, text",
    [
        ("account_servicing", "what is my balance"),
        ("product_info", "what is the overdraft fee"),
        ("dispute", "please dispute TXN0000001"),
    ],
)
async def test_graph_routes_to_expected_worker(worker, text):
    g = build_graph(
        supervisor_llm=FakeSupervisorLLM(worker),
        worker_llm=FakeWorkerLLM(),
        tools=default_tools(),
    )
    out = await g.ainvoke(new_state("C0001", text, max_steps=12))
    assert out["worker_results"][0]["worker"] == worker
    assert out["final_answer"]["answer"]


async def test_ambiguous_request_routes_to_intake():
    g = build_graph(
        supervisor_llm=FakeSupervisorLLM("account_servicing", needs_clarification=True),
        worker_llm=FakeWorkerLLM("Could you clarify what you need?"),
        tools=default_tools(),
    )
    out = await g.ainvoke(new_state("C0001", "help", max_steps=12))
    assert out["worker_results"][0]["worker"] == "intake"


async def test_out_of_scope_routes_to_escalation():
    g = build_graph(
        supervisor_llm=FakeSupervisorLLM("escalate_human"),
        worker_llm=FakeWorkerLLM(),
        tools=default_tools(),
    )
    out = await g.ainvoke(new_state("C0001", "wire money to my cousin overseas", max_steps=12))
    assert out["escalated"] is True
    assert out["final_answer"]["requires_human_review"] is True
