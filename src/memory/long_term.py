"""Long-term (cross-session) semantic memory (§7.1 Tiered memory, AC-05, §4 Memory).

Uses LangMem's create_memory_store_manager, backed by Gemini, to extract
durable facts (preferences, prior dispute references, last topic) into a
per-customer namespace, persisted via LangGraph's SQLite-backed BaseStore
(verified working: langgraph.store.sqlite.aio.AsyncSqliteStore at
STATE_DIR/memory.sqlite, gitignored — no external DB service, D-07/§3.4).
Semantic search over stored facts uses a local Sentence-Transformers embedding
(src/common/embeddings.py), so retrieval never calls an external service.
Values are masked before writing (NFR-05).

The extractor is swappable: the real LangMem manager for production and the
live cross-session test (P2-13's ``-m live`` variant), or a fake with the same
async call shape for the deterministic offline test suite (D-11) — this
matches the fallback plan.md itself anticipates in its Phase 2 risk notes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Protocol

from src.common.embeddings import EMBEDDING_DIMS, embed_texts
from src.common.masking import mask_obj, mask_text
from src.config import settings

NAMESPACE_PREFIX = "customer_memory"


def customer_namespace(customer_id: str) -> tuple[str, ...]:
    """Per-customer namespace so one customer's memories never leak into another's."""
    return (NAMESPACE_PREFIX, customer_id)


@asynccontextmanager
async def open_memory_store(conn_string: str | None = None) -> AsyncIterator[Any]:
    """Async context manager yielding an AsyncSqliteStore, configured with a
    local embedding index so asearch() does real semantic search rather than a
    no-op/exact-match fallback.

    Defaults to STATE_DIR/memory.sqlite (gitignored). Tests that need an
    isolated store should pass an explicit conn_string rather than
    monkeypatching STATE_DIR — see open_checkpointer()'s docstring for why
    that doesn't work (settings is a module-level singleton)."""
    from langgraph.store.sqlite.aio import AsyncSqliteStore

    settings.ensure_dirs()
    conn = conn_string or str(settings.state_dir / "memory.sqlite")
    index_config = {"dims": EMBEDDING_DIMS, "embed": embed_texts, "fields": ["content"]}
    async with AsyncSqliteStore.from_conn_string(conn, index=index_config) as store:
        await store.setup()
        yield store


async def remember(store: Any, customer_id: str, key: str, content: dict[str, Any]) -> None:
    """Directly persist one fact (masked). Used by write.py-style callers and
    by tests that don't want to invoke the full LLM extraction pipeline."""
    await store.aput(customer_namespace(customer_id), key, mask_obj(content))


def _extract_snippet(value: Any) -> str | None:
    """Pull the plain-text fact out of a stored value.

    Handles both shapes actually observed: a direct write via remember()/
    write_note() (``{"content": "text"}``) and LangMem's own extraction output
    (``{"kind": "Memory", "content": {"content": "text"}}`` — verified against
    a real live extraction run, not assumed).
    """
    if not isinstance(value, dict):
        return str(value) if value else None
    content = value.get("content")
    if isinstance(content, dict):
        content = content.get("content", content)
    if isinstance(content, str) and content:
        return content
    return str(content) if content else None


async def recall(store: Any, customer_id: str, query: str, *, limit: int = 5) -> list[str]:
    """Semantic search over a customer's stored facts; returns text snippets."""
    items = await store.asearch(customer_namespace(customer_id), query=query, limit=limit)
    return [s for item in items if (s := _extract_snippet(item.value))]


class Extractor(Protocol):
    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> Any: ...


def build_extractor(llm: Any, store: Any) -> Any:
    """Build the real LangMem extraction manager, bound to `store`.

    The manager's namespace uses LangMem's `{langgraph_user_id}` template, so
    calling it with config={"configurable": {"langgraph_user_id": customer_id}}
    (see extract_and_store) writes into exactly customer_namespace(customer_id).
    """
    from langmem import create_memory_store_manager

    return create_memory_store_manager(
        llm,
        namespace=(NAMESPACE_PREFIX, "{langgraph_user_id}"),
        store=store,
    )


def _mask_message(msg: Any) -> Any:
    """Mask a message's text content before it reaches the extractor.

    LangMem writes extracted facts straight to the store via its own internal
    call, bypassing mask_obj() entirely (confirmed against a real extraction
    run) — so anything it might remember verbatim from message content must
    already be masked going IN, or NFR-05 (never log a PAN in plaintext) could
    be violated by an automatically-extracted memory.
    """
    content = getattr(msg, "content", None)
    if isinstance(content, str) and hasattr(msg, "model_copy"):
        return msg.model_copy(update={"content": mask_text(content)})
    return msg


async def extract_and_store(extractor: Extractor, customer_id: str, messages: list[Any]) -> Any:
    """Run the extractor (real LangMem manager or a fake) over `messages`
    (masked first), writing whatever durable facts it finds into the
    customer's namespace."""
    masked = [_mask_message(m) for m in messages]
    return await extractor.ainvoke(
        {"messages": masked}, config={"configurable": {"langgraph_user_id": customer_id}}
    )
