"""Product-info worker: product, fee and servicing-policy questions (AC-03).

Answers only from policy_search (the agentic-RAG tool over data/policy_corpus)
with citations, and abstains rather than guessing when the corpus does not
support an answer -- policy_search itself handles grading, query rewrite and
the abstention decision (src/tools/rag_tool.py); this worker just calls it and
surfaces the result.
"""

from __future__ import annotations

from typing import Any

from src.agents._common import get_tool, latest_user_text, record_result
from src.context.isolate import isolate_for_worker
from src.tools.resilience import resilient_ainvoke


async def product_info_node(state: dict[str, Any], *, tools: list[Any], llm: Any) -> dict[str, Any]:
    iso = isolate_for_worker(state, "product_info")
    text = latest_user_text(iso)
    tool = get_tool(tools, "policy_search")
    if tool is None:
        return record_result(
            state, "product_info", "That capability is unavailable right now.", requires_human_review=True
        )

    result = await resilient_ainvoke(tool, {"query": text}, tool_name="policy_search")
    if isinstance(result, dict) and result.get("ok") is False:
        # resilient_ainvoke's own timeout/error failure shape
        return record_result(
            state, "product_info", "I couldn't look that up right now. Let me connect you to an agent.",
            requires_human_review=True,
        )

    answer = result.get("answer", "")
    citations = result.get("citations", [])
    abstained = result.get("abstained", False)
    return record_result(state, "product_info", answer, requires_human_review=abstained, citations=citations)
