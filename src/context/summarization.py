"""Context-engineering: summarization middleware (§7.1 Context engineering).

Once the estimated size of the older part of a conversation exceeds a token
threshold, replace it with a single LLM-produced summary message, keeping the
most recent turns verbatim so nothing recent is lost to summarization. Retries
transient errors via ainvoke_with_backoff (NFR-04) and normalizes Gemini 3.x
content via extract_text, matching the rest of the codebase's LLM-call pattern.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agents._common import extract_text
from src.context.select import estimate_tokens, message_text
from src.llm import ainvoke_with_backoff

DEFAULT_THRESHOLD_TOKENS = 1500
DEFAULT_KEEP_LAST = 4

SYSTEM = (
    "Summarize the following banking-servicing conversation history into one "
    "short paragraph capturing facts worth remembering: the customer's intent, "
    "account references already discussed (masked forms only), any dispute ids, "
    "and stated preferences. Never include a full account or card number."
)


async def maybe_summarize(
    llm: Any,
    messages: list[Any],
    *,
    threshold_tokens: int = DEFAULT_THRESHOLD_TOKENS,
    keep_last: int = DEFAULT_KEEP_LAST,
) -> list[Any]:
    """Summarize the older part of `messages` if it exceeds the token threshold.

    Returns `messages` unchanged if there is nothing old enough to summarize or
    the older portion is still under the threshold — summarization only ever
    runs when it is actually needed, to conserve LLM calls.
    """
    if len(messages) <= keep_last:
        return messages

    older, recent = messages[:-keep_last], messages[-keep_last:]
    older_text = "\n".join(message_text(m) for m in older)
    if estimate_tokens(older_text) < threshold_tokens:
        return messages

    resp = await ainvoke_with_backoff(
        llm, [SystemMessage(content=SYSTEM), HumanMessage(content=older_text)]
    )
    summary = extract_text(getattr(resp, "content", resp))
    return [AIMessage(content=f"[Earlier conversation summary]: {summary}"), *recent]
