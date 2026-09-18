"""Offline fakes for graph tests (no network, deterministic)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from src.schemas import RouteDecision


class _FakeStructured:
    def __init__(self, result: Any) -> None:
        self._result = result

    async def ainvoke(self, _messages: Any) -> Any:
        return self._result


class FakeSupervisorLLM:
    """with_structured_output(RouteDecision) returns a scripted decision."""

    def __init__(self, worker: str, *, needs_clarification: bool = False, reason: str = "test") -> None:
        self._decision = RouteDecision(
            worker=worker, reason=reason, needs_clarification=needs_clarification
        )

    def with_structured_output(self, _schema: Any) -> _FakeStructured:
        return _FakeStructured(self._decision)


class FakeWorkerLLM:
    """ainvoke() returns a fixed assistant message (no tool-calling loop).

    with_structured_output(schema) returns a fixed structured result: an
    explicit `structured_result`, or the schema's own no-argument default
    construction otherwise (e.g. ExtractedDisputeFields() -> transaction_id=None),
    so any worker that does a structured extraction still works with the
    plain, unconfigured fake.
    """

    def __init__(self, content: str = "Here is your answer.", structured_result: Any = None) -> None:
        self._content = content
        self._structured_result = structured_result

    async def ainvoke(self, _messages: Any) -> AIMessage:
        return AIMessage(content=self._content)

    def with_structured_output(self, schema: Any) -> _FakeStructured:
        result = self._structured_result if self._structured_result is not None else schema()
        return _FakeStructured(result)


class FakeTool:
    def __init__(self, name: str, result: Any | None = None) -> None:
        self.name = name
        self._result = result if result is not None else {"ok": True}

    async def ainvoke(self, _args: Any) -> Any:
        return self._result


def default_tools() -> list[FakeTool]:
    return [
        FakeTool("get_account_balance", {"balance": 100, "currency": "USD", "account_ref": "1945", "status": "active"}),
        FakeTool("list_recent_transactions", {"count": 0, "transactions": [], "account_ref": "1945"}),
        FakeTool("get_statement_summary", {"total_spend": 0, "by_category": {}, "account_ref": "1945"}),
        FakeTool("create_dispute_case", {"dispute_id": "DSP00001", "status": "draft"}),
        FakeTool(
            "check_dispute_eligibility",
            {"eligible": True, "window_days": 60, "days_since_transaction": 5, "explanation": ["within window"]},
        ),
        FakeTool(
            "policy_search",
            {"answer": "Fee information.", "citations": [{"doc_id": "POL-FEES", "section": "Overdraft Fee"}], "abstained": False},
        ),
    ]
