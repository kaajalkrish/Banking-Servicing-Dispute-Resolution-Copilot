"""Product-info worker: product, fee and servicing-policy questions (AC-03).

Answers only from policy_search (the agentic-RAG tool over data/policy_corpus)
with citations, and abstains rather than guessing when the corpus does not
support an answer -- policy_search itself handles grading, query rewrite and
the abstention decision (src/tools/rag_tool.py); this worker just calls it and
surfaces the result.

If policy_search abstains but there IS recalled customer memory available
(§7.1 Tiered memory), it gets one more chance from memory before giving up: a
real live run showed a question like "how would you reach me?" gets routed
here (not to account_servicing, which does read memory) and, without this,
silently threw away a correctly-recalled contact preference because
policy_search has no notion of per-customer memory at all. A structured
decision (not string-matching on the answer text) decides whether memory
actually answered the question.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from src.agents._common import get_tool, latest_user_text, memory_context_block, record_result
from src.context.isolate import isolate_for_worker
from src.llm import ainvoke_with_backoff

MEMORY_ANSWER_SYSTEM = (
    "Using ONLY the customer context provided (not general knowledge), decide "
    "whether it answers the customer's question. If it does, answer from it "
    "concisely; if it doesn't, set answered=false."
)


class MemoryAnswer(BaseModel):
    answered: bool
    answer: str = ""


async def _try_answer_from_memory(llm: Any, text: str, memory_block: str) -> str | None:
    structured = llm.with_structured_output(MemoryAnswer)
    decision: MemoryAnswer = await ainvoke_with_backoff(
        structured,
        [
            SystemMessage(content=MEMORY_ANSWER_SYSTEM),
            HumanMessage(content=f"Customer asked: {text}\n{memory_block}"),
        ],
    )
    return decision.answer if decision.answered else None


async def product_info_node(state: dict[str, Any], *, tools: list[Any], llm: Any) -> dict[str, Any]:
    iso = isolate_for_worker(state, "product_info")
    text = latest_user_text(iso)
    tool = get_tool(tools, "policy_search")
    if tool is None:
        return record_result(
            state, "product_info", "That capability is unavailable right now.", requires_human_review=True
        )

    # tool is already resilient + logged (P3-07 registry) — just invoke.
    result = await tool.ainvoke({"query": text})
    if isinstance(result, dict) and result.get("ok") is False:
        # the ResilientTool wrapper's own timeout/error failure shape
        return record_result(
            state, "product_info", "I couldn't look that up right now. Let me connect you to an agent.",
            requires_human_review=True,
        )

    answer = result.get("answer", "")
    citations = result.get("citations", [])
    abstained = result.get("abstained", False)

    memory_block = memory_context_block(iso)
    if abstained and memory_block:
        memory_answer = await _try_answer_from_memory(llm, text, memory_block)
        if memory_answer:
            return record_result(state, "product_info", memory_answer, citations=[])

    return record_result(state, "product_info", answer, requires_human_review=abstained, citations=citations)
