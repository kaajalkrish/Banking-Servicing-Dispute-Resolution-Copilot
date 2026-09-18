"""Tests for the memory/context nodes wired into the graph (P2-12).

Offline: uses a real (temp-dir) AsyncSqliteStore for actual recall/save
behaviour, but fake LLMs/extractors — no network. Verifies:
- omitting memory_store leaves the graph's behaviour unchanged (backward
  compatibility with every routing/loop test written before this phase).
- a pre-seeded long-term fact is recalled and actually reaches the worker's
  prompt (not just stored in state and unused).
- save_memory_node runs exactly once at the end, scoped to the right customer.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from src.graph import build_graph, open_checkpointer, run_config
from src.memory.long_term import open_memory_store, remember
from src.state import new_state
from tests._fakes import FakeSupervisorLLM, FakeWorkerLLM, default_tools


async def test_graph_without_memory_store_is_unchanged():
    """No memory_store => no memory/context keys, same as pre-P2-12 behaviour."""
    g = build_graph(
        supervisor_llm=FakeSupervisorLLM("account_servicing"),
        worker_llm=FakeWorkerLLM("Balance is 100."),
        tools=default_tools(),
    )
    out = await g.ainvoke(new_state("C0001", "what is my balance", max_steps=12))
    assert "memory" not in out or not out.get("memory")
    assert "context" not in out or not out.get("context")
    assert out["final_answer"]["answer"] == "Balance is 100."


async def test_recalled_memory_reaches_worker_prompt(tmp_path):
    captured: list[str] = []

    class CapturingWorkerLLM:
        async def ainvoke(self, messages):
            captured.append(str(messages[-1].content))
            return AIMessage(content="Your balance is 100 USD.")

    async with (
        open_memory_store(str(tmp_path / "memory.sqlite")) as mstore,
        open_checkpointer(str(tmp_path / "checkpoints.sqlite")) as cstore,
    ):
        await remember(mstore, "C0001", "pref-1", {"content": "Customer prefers to be called Mr. Smith."})

        g = build_graph(
            supervisor_llm=FakeSupervisorLLM("account_servicing"),
            worker_llm=CapturingWorkerLLM(),
            tools=default_tools(),
            checkpointer=cstore,
            memory_store=mstore,
        )
        out = await g.ainvoke(
            new_state("C0001", "what is my balance", max_steps=12), run_config("MEM-T1")
        )

    assert "Mr. Smith" in out["memory"]["recalled"][0]
    assert "Mr. Smith" in out["context"]["memories"][0]
    assert any("Mr. Smith" in p for p in captured), "recalled memory never reached the worker prompt"


async def test_save_memory_runs_once_scoped_to_customer(tmp_path):
    calls: list[tuple[list, dict]] = []

    class FakeExtractor:
        async def ainvoke(self, state, config=None):
            calls.append((state["messages"], config))
            return []

    async with (
        open_memory_store(str(tmp_path / "memory.sqlite")) as mstore,
        open_checkpointer(str(tmp_path / "checkpoints.sqlite")) as cstore,
    ):
        g = build_graph(
            supervisor_llm=FakeSupervisorLLM("account_servicing"),
            worker_llm=FakeWorkerLLM("Balance is 100."),
            tools=default_tools(),
            checkpointer=cstore,
            memory_store=mstore,
            memory_extractor=FakeExtractor(),
        )
        await g.ainvoke(new_state("C0001", "what is my balance", max_steps=12), run_config("MEM-T2"))

    assert len(calls) == 1
    messages, config = calls[0]
    assert config["configurable"]["langgraph_user_id"] == "C0001"
    assert len(messages) == 2  # human turn + assistant reply
