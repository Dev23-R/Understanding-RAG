---
tags: [concept, vector-store]
---

# 04 — The Vector Store Is One Matrix Multiply

## Why this project doesn't use Chroma, FAISS, or Qdrant

Deliberately. `src/store.py` is about 120 lines of numpy.

A vector store does exactly two things:

1. Keep a matrix of embeddings.
2. Find the rows most similar to a query vector.

Everything else a vector database offers — persistence, sharding, metadata
filtering, approximate search, hybrid scoring, a network API, replication — is
*engineering around those two operations*, not a different idea.

Written out, "semantic search" is **one matrix multiply and an argsort**. Seeing
that is the difference between using RAG and understanding it. Reach for Chroma
first and the core stays a black box you have opinions about but no model of.

## The entire search

```python
scores = self.embeddings @ query_vector
```

That's it. Shape `(53, 384) @ (384,)` → `(53,)`, one score per chunk.

It works because both sides are unit-normalised (see
[[03 - Embeddings and the Query-Passage Asymmetry]]). For unit vectors the dot
product *is* the cosine of the angle between them. So a single BLAS call computes
every similarity in the corpus at once.

Then:

```python
k = min(top_k, len(scores))
top_unsorted = np.argpartition(-scores, k - 1)[:k]
top_sorted = top_unsorted[np.argsort(-scores[top_unsorted])]
```

`argpartition` finds the top-k without fully sorting — O(n) instead of O(n log n).
At 53 chunks this is irrelevant; at a million it isn't, and it costs nothing to
do it correctly.

## Score interpretation

Cosine lands in `[-1, 1]`: 1 is identical direction, 0 is unrelated, negative is
opposed.

In practice you almost never see text-embedding scores below about 0.1. Real
signal sits in a narrow band — on this corpus, roughly **0.48 to 0.84**. That
compression is why `MIN_SIMILARITY` has to be tuned per model rather than set to
something intuitive like 0.5, and why it doesn't do the job people expect of it
([[Similarity Thresholds Do Not Separate]]).

## When you actually need a real vector database

Exact search is O(n) per query. At some scale that stops being free:

| Corpus size | Exact search | Verdict |
|---|---|---|
| < 10k chunks | sub-millisecond | numpy is genuinely fine |
| 10k – 100k | a few ms | fine for most apps |
| 100k – 1M | 10–100 ms | consider FAISS / an ANN index |
| > 1M | too slow | you need ANN, and probably a real database |

Approximate nearest neighbour indexes (HNSW, IVF) trade a small amount of recall
for enormous speed. At our scale the approximation would only cost accuracy for
no benefit.

The other reasons to reach for a real database are operational, not
algorithmic: concurrent writes, metadata filtering at scale, replication,
multi-tenancy, not having to reindex from scratch on every change.

## Persistence: .npy + JSON, not pickle

Two files:

- `index/embeddings.npy` — the matrix
- `index/chunks.json` — chunk text, metadata, and the model identity

Not pickle, because **pickle executes arbitrary code on load**. That's a poor
property for a file you might later receive from a colleague or pull from a
build artifact.

### The model-identity guard

`chunks.json` records which embedding model built the index, and `load()` refuses
to proceed if `config.EMBEDDING_MODEL` has changed:

```python
if stored_model != config.EMBEDDING_MODEL:
    raise ValueError(...)
```

This matters more than it looks. Embeddings from different models aren't "less
accurate" together — they're **meaningless** together. The two models carve up
their vector spaces completely differently; there's no shared coordinate system.
Query a bge-small index with a MiniLM vector and you get well-formed, confidently
ranked nonsense, with no error to tell you.

Swapping the model in config and forgetting to reindex is an easy mistake, and
without this guard it produces a system that looks like it works and doesn't.
The index directory is gitignored for the same family of reason: a derived
artifact that can silently disagree with the source it claims to represent
shouldn't be committed.

## Things to try

- Print the full score distribution for a query — not just the top 5 — and see
  how quickly it decays.
- Change `EMBEDDING_MODEL` in `config.py` *without* rebuilding, and run
  `scripts.ask`. Confirm the guard fires. Then imagine finding that bug without it.

---
Next: [[05 - Dense vs Lexical vs Hybrid]]
