"""Maps OpenInference span kinds to the three latency classes used by golden
signals (D-05, §7.3): thinking / acting / tool.

Verified against real captured spans from two live graph runs, not assumed:

- ``LLM`` spans (e.g. ``ChatGoogleGenerativeAI``) -> **thinking**.
- ``TOOL`` spans (e.g. ``get_account_balance``, a real LangChain tool loaded
  via langchain-mcp-adapters) -> **tool**. ``RETRIEVER`` also maps here per
  D-05, though in practice our RAG tool (a plain Python class, not a
  LangChain ``BaseRetriever``) never produced a ``RETRIEVER``-kind span — its
  internal Chroma query and answer-composition call surfaced as ``CHAIN``/
  ``LLM`` instead.
- Everything else -> **acting**: this is where ``CHAIN`` spans land —
  ``LangGraph`` itself, every graph node (``supervisor``, ``account_servicing``,
  ``finalize``, the RAG subgraph's own ``retrieve``/``grade``/``answer`` nodes),
  and LangChain plumbing (``RunnableSequence``, ``PydanticOutputParser``).
  ``AGENT`` also maps here per D-05, though it never appeared in practice —
  our nodes are plain async functions, not LangChain's ``AgentExecutor``.
"""

from __future__ import annotations

from typing import Literal

SpanClass = Literal["thinking", "acting", "tool"]

_THINKING_KINDS = frozenset({"LLM"})
_TOOL_KINDS = frozenset({"TOOL", "RETRIEVER"})
# Everything else (CHAIN, AGENT, and any unrecognised kind) is "acting":
# graph-node orchestration, not a model call or an external tool/retrieval.


def classify_span_kind(span_kind: str | None) -> SpanClass:
    """Map one OpenInference span_kind value to thinking/acting/tool."""
    kind = (span_kind or "").upper()
    if kind in _THINKING_KINDS:
        return "thinking"
    if kind in _TOOL_KINDS:
        return "tool"
    return "acting"


def classify_spans_dataframe(df):
    """Add a 'span_class' column (thinking/acting/tool) to a Phoenix spans
    dataframe. Used by the Phase 5 golden-signals script to split latency."""
    return df.assign(span_class=df["span_kind"].map(classify_span_kind))
