"""The vector store.

This is deliberately ~120 lines of numpy rather than an import of Chroma, FAISS,
Qdrant or LanceDB. The reason is pedagogical and worth stating plainly:

A vector store does exactly two things. It keeps a matrix of embeddings, and it
finds the rows most similar to a query vector. Everything else a vector database
offers -- persistence, sharding, metadata filtering, approximate search, hybrid
scoring, a network API -- is engineering around those two operations, not a
different idea.

Written out, "semantic search" is one matrix multiply and an argsort. Seeing that
is the difference between using RAG and understanding it. A production system on
10 million chunks genuinely needs FAISS or a real database, because exact search
is O(n) per query and approximate indexes (HNSW, IVF) trade a little recall for
enormous speed. On our scale -- a few hundred chunks -- exact search takes
microseconds and the approximation would only cost accuracy.

The persistence format is `.npy` plus a JSON sidecar rather than pickle. Pickle
executes arbitrary code on load, which is a poor property for a file you might
later download from a colleague.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import config
from .chunking import Chunk


class VectorStore:
    """An exact-search vector index over chunk embeddings."""

    def __init__(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        if len(chunks) != embeddings.shape[0]:
            raise ValueError(
                f"Chunk/embedding count mismatch: {len(chunks)} chunks, "
                f"{embeddings.shape[0]} embeddings. The index is corrupt; rebuild it."
            )
        self.chunks = chunks
        self.embeddings = embeddings

    def __len__(self) -> int:
        return len(self.chunks)

    # --- Search -----------------------------------------------------------

    def search(self, query_vector: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        """Return (chunk_index, similarity) for the top_k nearest chunks.

        The whole search is the line `self.embeddings @ query_vector`.

        That works because both sides are unit-normalised (see embedding.py).
        For unit vectors, the dot product *is* the cosine of the angle between
        them: cos(theta) = (a . b) / (|a| |b|), and |a| = |b| = 1.

        So one matrix multiply of shape (n_chunks, 384) @ (384,) gives every
        similarity at once, in a single BLAS call. Scores land in [-1, 1], where
        1 means identical direction and 0 means unrelated. In practice for text
        embeddings you rarely see anything below about 0.1 -- the useful signal
        sits in a narrow band, which is exactly why MIN_SIMILARITY has to be
        tuned per model rather than set to something intuitive like 0.5.
        """
        if len(self.chunks) == 0:
            return []

        scores = self.embeddings @ query_vector

        # argpartition finds the top_k without fully sorting all n scores --
        # O(n) instead of O(n log n). At our scale this is irrelevant; at a
        # million chunks it is not, and it costs nothing to do it right.
        k = min(top_k, len(scores))
        top_unsorted = np.argpartition(-scores, k - 1)[:k]
        top_sorted = top_unsorted[np.argsort(-scores[top_unsorted])]

        return [(int(i), float(scores[i])) for i in top_sorted]

    # --- Persistence ------------------------------------------------------

    def save(self, index_dir: Path | None = None) -> Path:
        index_dir = index_dir or config.INDEX_DIR
        index_dir.mkdir(parents=True, exist_ok=True)

        np.save(index_dir / "embeddings.npy", self.embeddings)

        payload = {
            # The model name is stored with the index because embeddings from
            # different models are not comparable -- not "less accurate",
            # meaningless. Loading a bge-small index and querying it with a
            # MiniLM vector returns confident nonsense. We check on load.
            "embedding_model": config.EMBEDDING_MODEL,
            "embedding_dim": int(self.embeddings.shape[1]),
            "chunk_count": len(self.chunks),
            "chunks": [asdict(c) for c in self.chunks],
        }
        # `default=str` handles YAML frontmatter values that PyYAML parses into
        # Python objects rather than strings -- `last_reviewed: 2026-07-14`
        # becomes a `datetime.date`, which json.dumps refuses. Stringifying is
        # right here because this metadata is for display and filtering, not
        # arithmetic.
        (index_dir / "chunks.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return index_dir

    @classmethod
    def load(cls, index_dir: Path | None = None) -> "VectorStore":
        index_dir = index_dir or config.INDEX_DIR

        chunks_file = index_dir / "chunks.json"
        embeddings_file = index_dir / "embeddings.npy"

        if not chunks_file.exists() or not embeddings_file.exists():
            raise FileNotFoundError(
                f"No index at {index_dir}. Build one first:\n"
                f"    .venv\\Scripts\\python.exe -m scripts.index"
            )

        payload = json.loads(chunks_file.read_text(encoding="utf-8"))

        stored_model = payload.get("embedding_model")
        if stored_model != config.EMBEDDING_MODEL:
            raise ValueError(
                f"Index was built with '{stored_model}' but config specifies "
                f"'{config.EMBEDDING_MODEL}'. Vectors from different models are "
                f"not comparable -- you would get confident nonsense. Rebuild "
                f"the index."
            )

        embeddings = np.load(embeddings_file)
        chunks = [Chunk(**c) for c in payload["chunks"]]
        return cls(chunks, embeddings)
