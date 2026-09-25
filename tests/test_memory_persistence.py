"""Cross-session (tiered) memory persistence test (§7.1 Tiered memory, AC-05).

Simulates a customer returning after their session ended: "session 1" states a
fact and the memory store is then FULLY CLOSED (not just reused in-process);
"session 2" reopens the same on-disk store under a new thread and recalls it —
proving genuine durable persistence, not just an in-memory object surviving
within one test.

Two variants (D-11):
- test_cross_session_recall_offline (default, deterministic): a fake
  extractor stands in for LangMem, and the recall is proven to actually reach
  a worker's LLM prompt through the real graph — no network.
- test_cross_session_recall_live (@pytest.mark.live): the REAL LangMem +
  Gemini extraction pipeline (gemini-3.5-flash-lite, to conserve the
  daily-limited flash-tier quota), and writes the committed evidence log
  logs/memory_test.log (masked) — this is P2-15's evidence commit.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.common.masking import mask_text
from src.memory.long_term import build_extractor, extract_and_store, open_memory_store, recall

CUSTOMER_ID = "C0001"
SESSION_1_MESSAGES = [
    HumanMessage(content="Please always contact me by email, not by phone."),
    AIMessage(content="Understood, I will use email going forward."),
]
RECALL_QUERY = "how does this customer want to be contacted"


def _setup_masked_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"memory_test.{log_path.name}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # avoid duplicate handlers if this module is imported twice
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return logger


def _log_masked(logger: logging.Logger | None, message: str) -> None:
    if logger is not None:
        logger.info(mask_text(message))


async def _write_session_1(db_path: str, extractor_factory, logger: logging.Logger | None) -> None:
    """Session 1: state a preference, extract it, then fully close the store."""
    async with open_memory_store(db_path) as store:
        extractor = extractor_factory(store)
        _log_masked(logger, f"session 1 (thread=session-1): stating a preference for {CUSTOMER_ID}")
        await extract_and_store(extractor, CUSTOMER_ID, SESSION_1_MESSAGES)
        _log_masked(logger, "session 1 complete; store closing")
    # `store` is now fully closed — nothing kept in-memory between sessions.


class _FakeLangMemExtractor:
    """Deterministic stand-in for LangMem: recognises a contact-preference
    statement and writes it via the same store the real manager would use, so
    the offline test exercises the extractor->store call shape without Gemini."""

    def __init__(self, store) -> None:
        self._store = store

    async def ainvoke(self, state: dict, config: dict | None = None) -> list:
        customer_id = config["configurable"]["langgraph_user_id"]
        text = " ".join(
            getattr(m, "content", "") for m in state["messages"] if getattr(m, "type", None) == "human"
        )
        if "email" in text.lower():
            await self._store.aput(
                ("customer_memory", customer_id), "fake-pref", {"content": "Customer prefers contact by email."}
            )
        return []


async def test_cross_session_recall_offline(tmp_path):
    """Fake extractor + real store; proves the recalled fact reaches a
    worker's LLM prompt through the actual graph, not just recall() in
    isolation (test_graph_memory_wiring.py already covers the simpler case of
    a directly-seeded fact; this one goes through the extractor and a real
    session close/reopen)."""
    from src.graph import build_graph, open_checkpointer, run_config
    from src.state import new_state
    from tests._fakes import FakeSupervisorLLM, default_tools

    db_path = str(tmp_path / "memory.sqlite")
    cp_path = str(tmp_path / "checkpoints.sqlite")

    await _write_session_1(db_path, lambda store: _FakeLangMemExtractor(store), logger=None)

    captured: list[str] = []

    class CapturingWorkerLLM:
        async def ainvoke(self, messages):
            captured.append(str(messages[-1].content))
            return AIMessage(content="I will contact you by email as you prefer.")

    async with (
        open_memory_store(db_path) as mstore,
        open_checkpointer(cp_path) as cstore,
    ):
        graph = build_graph(
            supervisor_llm=FakeSupervisorLLM("account_servicing"),
            worker_llm=CapturingWorkerLLM(),
            tools=default_tools(),
            checkpointer=cstore,
            memory_store=mstore,
        )
        out = await graph.ainvoke(
            new_state(CUSTOMER_ID, "How would you contact me about an account issue?", max_steps=12),
            run_config("session-2-thread"),
        )

    assert any("email" in r.lower() for r in out["memory"]["recalled"])
    assert any("email" in p.lower() for p in captured), "recalled preference never reached the worker prompt"


@pytest.mark.live
async def test_cross_session_recall_live(tmp_path):
    """Real LangMem + real Gemini (flash-lite tier). Writes the committed
    evidence log; the sqlite database itself stays in a temp dir (never a
    binary file is committed) — the log is the evidence artifact."""
    from src.llm import get_llm

    log_path = Path("logs") / "memory_test.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = _setup_masked_logger(log_path)

    db_path = str(tmp_path / "memory.sqlite")
    llm = get_llm("fast")  # gemini-3.5-flash-lite: conserves the daily-limited flash quota

    await _write_session_1(db_path, lambda store: build_extractor(llm, store), logger=logger)

    async with open_memory_store(db_path) as store:
        _log_masked(logger, f"session 2 (thread=session-2, new session, store reopened): querying for {CUSTOMER_ID}")
        recalled = await recall(store, CUSTOMER_ID, RECALL_QUERY, limit=5)
        for r in recalled:
            _log_masked(logger, f"  recalled: {r}")

    found = any("email" in r.lower() for r in recalled)
    _log_masked(
        logger,
        "PASS: cross-session recall verified with real Gemini + LangMem"
        if found
        else f"FAIL: expected an email-contact-preference fact, got: {recalled}",
    )
    for handler in logger.handlers:
        handler.flush()
    assert found, f"live cross-session recall did not find the stated preference: {recalled}"
