"""Agentic-RAG tool: retrieval-in-the-loop over the policy corpus (§7.1, AC-03).

Implemented as a small compiled LangGraph subgraph — retrieve -> grade
relevance -> rewrite query (bounded) -> answer with citations, or a structured
abstention — rather than a single retrieve-then-answer call, so a weak first
retrieval gets one or two chances to be rephrased before the tool gives up and
abstains (never guesses).

Grading combines a cheap distance-threshold check (calibrated against the real
index: an on-topic query like "overdraft fee" scores ~0.13, an out-of-scope
one like "cryptocurrency wallets" scores ~0.65) with an LLM grader only for the
borderline band in between — most queries never need an LLM call to be graded,
which conserves quota/cost.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, PrivateAttr
from typing_extensions import TypedDict

from src.agents._common import extract_text
from src.llm import ainvoke_with_backoff
from src.tools.rag_index import get_collection

# Calibrated against a real build of the corpus (see rag_index commit): well
# supported queries land well under 0.35; clearly out-of-scope queries land
# well over 0.55. The band between is genuinely ambiguous and gets an LLM grade.
CONFIDENT_DISTANCE = 0.35
POOR_DISTANCE = 0.55
DEFAULT_TOP_K = 3
DEFAULT_MAX_REWRITES = 2

ABSTENTION_MESSAGE = (
    "I don't have information about that in our policy documentation, so I "
    "don't want to guess. I can connect you with a servicing agent who can "
    "help, or you can ask about fees, disputes, transfers, cards, statements, "
    "account types or KYC."
)

GRADE_SYSTEM = (
    "You judge whether a retrieved banking-policy passage actually answers the "
    "customer's question. Answer strictly from whether the passage is on-topic "
    "and sufficient -- do not use outside knowledge."
)
REWRITE_SYSTEM = (
    "The previous search of the banking-policy corpus found nothing good enough. "
    "Rewrite the customer's question as a short, more specific or differently "
    "phrased search query likely to match a policy document section. Return "
    "only the rewritten query text, nothing else."
)
ANSWER_SYSTEM = (
    "Answer the customer's question using ONLY the retrieved policy passages "
    "below. Cite the source of every claim inline as [doc_id §section]. If the "
    "passages do not fully answer the question, say what is and is not covered "
    "-- never state something the passages do not support."
)


class GradeDecision(BaseModel):
    relevant: bool = Field(description="True if the passage sufficiently answers the question.")
    reason: str = ""


class RetrievedChunk(TypedDict):
    doc_id: str
    section: str
    text: str
    distance: float


class RagState(TypedDict, total=False):
    query: str
    original_query: str
    rewrite_count: int
    max_rewrites: int
    top_k: int
    retrieved: list[RetrievedChunk]
    grade: Literal["confident", "poor", "borderline_accept", "borderline_reject"]
    answer: str
    citations: list[dict[str, str]]
    abstained: bool


def _query_collection(collection: Any, query: str, top_k: int) -> list[RetrievedChunk]:
    result = collection.query(
        query_texts=[query], n_results=top_k, include=["documents", "metadatas", "distances"]
    )
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]
    return [
        {"doc_id": m["doc_id"], "section": m["section"], "text": d, "distance": float(dist)}
        for d, m, dist in zip(docs, metas, dists)
    ]


async def retrieve_node(state: RagState, *, collection: Any) -> dict[str, Any]:
    retrieved = _query_collection(collection, state["query"], state.get("top_k", DEFAULT_TOP_K))
    return {"retrieved": retrieved}


async def grade_node(state: RagState, *, llm: Any) -> dict[str, Any]:
    retrieved = state.get("retrieved", [])
    if not retrieved:
        return {"grade": "poor"}
    best = retrieved[0]
    if best["distance"] <= CONFIDENT_DISTANCE:
        return {"grade": "confident"}
    if best["distance"] >= POOR_DISTANCE:
        return {"grade": "poor"}
    # Borderline: ask an LLM grader rather than guess from distance alone.
    structured = llm.with_structured_output(GradeDecision)
    decision: GradeDecision = await ainvoke_with_backoff(
        structured,
        [
            SystemMessage(content=GRADE_SYSTEM),
            HumanMessage(
                content=f"Question: {state['original_query']}\n\nPassage:\n{best['text']}"
            ),
        ],
    )
    return {"grade": "borderline_accept" if decision.relevant else "borderline_reject"}


async def rewrite_node(state: RagState, *, llm: Any) -> dict[str, Any]:
    resp = await ainvoke_with_backoff(
        llm,
        [
            SystemMessage(content=REWRITE_SYSTEM),
            HumanMessage(content=state["original_query"]),
        ],
    )
    new_query = extract_text(getattr(resp, "content", resp)).strip() or state["original_query"]
    return {"query": new_query, "rewrite_count": state.get("rewrite_count", 0) + 1}


async def answer_node(state: RagState, *, llm: Any) -> dict[str, Any]:
    retrieved = state.get("retrieved", [])
    context = "\n\n".join(f"[{c['doc_id']} §{c['section']}]\n{c['text']}" for c in retrieved)
    resp = await ainvoke_with_backoff(
        llm,
        [
            SystemMessage(content=ANSWER_SYSTEM),
            HumanMessage(content=f"Question: {state['original_query']}\n\nPassages:\n{context}"),
        ],
    )
    answer = extract_text(getattr(resp, "content", resp))
    citations = [{"doc_id": c["doc_id"], "section": c["section"]} for c in retrieved]
    return {"answer": answer, "citations": citations, "abstained": False}


def abstain_node(_state: RagState) -> dict[str, Any]:
    return {"answer": ABSTENTION_MESSAGE, "citations": [], "abstained": True}


def route_after_grade(state: RagState) -> str:
    if state.get("grade") in ("confident", "borderline_accept"):
        return "answer"
    if state.get("rewrite_count", 0) < state.get("max_rewrites", DEFAULT_MAX_REWRITES):
        return "rewrite"
    return "abstain"


def build_rag_subgraph(*, collection: Any, grader_llm: Any, rewriter_llm: Any, answer_llm: Any):
    g = StateGraph(RagState)
    g.add_node("retrieve", partial(retrieve_node, collection=collection))
    g.add_node("grade", partial(grade_node, llm=grader_llm))
    g.add_node("rewrite", partial(rewrite_node, llm=rewriter_llm))
    g.add_node("answer", partial(answer_node, llm=answer_llm))
    g.add_node("abstain", abstain_node)

    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges(
        "grade", route_after_grade, {"answer": "answer", "rewrite": "rewrite", "abstain": "abstain"}
    )
    g.add_edge("rewrite", "retrieve")
    g.add_edge("answer", END)
    g.add_edge("abstain", END)
    return g.compile()


class PolicySearchInput(BaseModel):
    query: str = Field(description="The customer's question to search the policy corpus for.")


class PolicySearchTool(BaseTool):
    """A genuine ``langchain_core.tools.BaseTool`` subclass — not just a
    duck-typed ``.name`` + ``.ainvoke()`` object — so OpenInference's LangChain
    auto-instrumentation recognises calls to it as a TOOL-kind span (verified:
    an earlier plain-class version produced no span at all for this tool,
    since the instrumentor only recognises real ``BaseTool``/``BaseRetriever``
    invocations; the RAG subgraph's own internal nodes showed up as
    CHAIN/LLM instead, which is still true for THEIR spans, but the outer
    ``policy_search`` call itself is now traced correctly)."""

    name: str = "policy_search"
    description: str = (
        "Search the banking policy corpus for an answer to a customer's "
        "product, fee or servicing-policy question. Returns citations, or "
        "abstains if the corpus does not support an answer."
    )
    args_schema: type[BaseModel] = PolicySearchInput

    _graph: Any = PrivateAttr()
    _top_k: int = PrivateAttr()
    _max_rewrites: int = PrivateAttr()

    def __init__(
        self,
        *,
        collection: Any = None,
        llm: Any = None,
        top_k: int = DEFAULT_TOP_K,
        max_rewrites: int = DEFAULT_MAX_REWRITES,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        col = collection if collection is not None else get_collection()
        self._graph = build_rag_subgraph(collection=col, grader_llm=llm, rewriter_llm=llm, answer_llm=llm)
        self._top_k = top_k
        self._max_rewrites = max_rewrites

    def _run(self, query: str) -> dict[str, Any]:
        raise NotImplementedError("PolicySearchTool is async-only; use ainvoke().")

    async def _arun(self, query: str) -> dict[str, Any]:
        initial: RagState = {
            "query": query,
            "original_query": query,
            "rewrite_count": 0,
            "max_rewrites": self._max_rewrites,
            "top_k": self._top_k,
        }
        out = await self._graph.ainvoke(initial, {"recursion_limit": 25})
        return {
            "answer": out.get("answer", ABSTENTION_MESSAGE),
            "citations": out.get("citations", []),
            "abstained": out.get("abstained", True),
        }
