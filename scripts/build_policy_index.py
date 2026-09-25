"""Build (or rebuild) the Chroma index over the synthetic policy corpus.

Idempotent: chunk ids are deterministic, so re-running this after editing a
policy doc just upserts the changed chunks rather than duplicating them.

Usage:
    python scripts/build_policy_index.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.tools.rag_index import (
    DEFAULT_COLLECTION,
    DEFAULT_CORPUS_DIR,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_PERSIST_DIR,
    index_corpus,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the policy-corpus Chroma index.")
    ap.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    ap.add_argument("--persist-dir", type=Path, default=DEFAULT_PERSIST_DIR)
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    args = ap.parse_args()

    n = index_corpus(args.corpus_dir, args.persist_dir, args.collection, args.model)
    print(f"indexed {n} chunks from {args.corpus_dir} -> {args.persist_dir} (collection={args.collection!r})")


if __name__ == "__main__":
    main()
