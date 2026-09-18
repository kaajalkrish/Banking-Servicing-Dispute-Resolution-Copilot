"""Shared local Sentence-Transformers embedding helper (§4 Retrieval — local).

Used by the long-term memory store's semantic index (src/memory/long_term.py).
The RAG index (src/tools/rag_index.py) uses the same model via chromadb's own
embedding-function wrapper; this module exists so the memory store — which
needs a plain ``Sequence[str] -> list[list[float]]`` callable for LangGraph's
``IndexConfig`` — shares the same cached model instance rather than loading a
second copy of the weights.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMS = 384  # all-MiniLM-L6-v2's published output dimensionality


@lru_cache(maxsize=2)
def _get_model(model_name: str = DEFAULT_MODEL):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_texts(texts: Sequence[str], model_name: str = DEFAULT_MODEL) -> list[list[float]]:
    """Embed a sequence of strings. Matches LangGraph's EmbeddingsFunc shape."""
    return _get_model(model_name).encode(list(texts)).tolist()
