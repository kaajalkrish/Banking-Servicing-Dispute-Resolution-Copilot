"""Chroma index over the synthetic banking-policy corpus (§7.1 Agentic-RAG tool).

Chunking is by heading (each ``## Section`` becomes one chunk) with doc_id,
section, version and effective_date attached as metadata. Chunk ids are
deterministic (``{doc_id}::{section-slug}``), so re-running the indexer is
idempotent and citations stay stable across rebuilds. Embeddings use a local
Sentence-Transformers model (§4 Retrieval — local, no external service).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)

DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "policy_corpus"
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chroma"
DEFAULT_COLLECTION = "policy_corpus"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    section: str
    title: str
    version: str
    effective_date: str
    text: str


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    m = _FRONT_MATTER_RE.match(raw)
    if not m:
        raise ValueError("policy doc missing YAML-style front-matter block")
    fm_block, body = m.group(1), m.group(2)
    fm = dict(line.split(": ", 1) for line in fm_block.splitlines() if ": " in line)
    return fm, body


def parse_policy_doc(path: Path) -> list[Chunk]:
    """Parse one policy markdown file into one Chunk per ``## `` section."""
    raw = path.read_text(encoding="utf-8")
    fm, body = _parse_front_matter(raw)
    doc_id = fm["doc_id"]
    title = fm["title"]
    version = fm["version"]
    effective_date = fm["effective_date"]

    headings = list(_HEADING_RE.finditer(body))
    chunks: list[Chunk] = []
    for i, m in enumerate(headings):
        section = m.group(1).strip()
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        section_text = body[start:end].strip()
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}::{_slug(section)}",
                doc_id=doc_id,
                section=section,
                title=title,
                version=version,
                effective_date=effective_date,
                text=f"{title} — {section}\n\n{section_text}",
            )
        )
    return chunks


def chunk_policy_corpus(corpus_dir: Path = DEFAULT_CORPUS_DIR) -> list[Chunk]:
    """Chunk every ``*.md`` file in the corpus directory."""
    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        chunks.extend(parse_policy_doc(path))
    return chunks


def _embedding_function(model_name: str = DEFAULT_EMBEDDING_MODEL):
    from chromadb.utils import embedding_functions

    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)


def get_collection(
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
):
    """Open (or create) the persistent Chroma collection for the policy corpus."""
    import chromadb

    persist_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist_dir))
    return client.get_or_create_collection(
        name=collection_name, embedding_function=_embedding_function(model_name)
    )


def index_corpus(
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> int:
    """(Re)build the Chroma index from the corpus. Idempotent (deterministic ids)."""
    chunks = chunk_policy_corpus(corpus_dir)
    collection = get_collection(persist_dir, collection_name, model_name)
    collection.upsert(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "doc_id": c.doc_id,
                "section": c.section,
                "title": c.title,
                "version": c.version,
                "effective_date": c.effective_date,
            }
            for c in chunks
        ],
    )
    return len(chunks)
