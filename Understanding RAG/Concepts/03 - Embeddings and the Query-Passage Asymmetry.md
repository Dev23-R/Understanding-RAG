---
tags: [concept, embeddings]
---

# 03 — Embeddings and the Query-Passage Asymmetry

## What an embedding is

A fixed-length list of floats — 384 of them for `bge-small-en-v1.5` — positioned
so that texts with similar meaning sit close together in that 384-dimensional
space.

That's the whole trick behind semantic search. You cannot compare a question to a
document by string matching when they share no words. You *can* compare their
positions.

"What do I do when the queue backs up?" and "Atlas has no backpressure; once the
queue is growing faster than it drains it will not recover" share almost no
vocabulary. Their embeddings are close because the model was trained to put
related meanings near each other.

## The asymmetry — the part that silently costs you accuracy

This is the single most common invisible bug when using BGE-family models.

BGE models are trained on **(query, passage) pairs where the two sides are
encoded differently**:

- Queries carry an instruction prefix: `"Represent this sentence for searching relevant passages: "`
- Passages carry **no prefix at all**

The model learns to map a prefixed query into the same neighbourhood as the
*unprefixed* text of the passage that answers it.

If you prefix both, or neither, retrieval still runs. You still get ranked
results. They're just measurably worse — and **nothing in the output tells you
why**. You'd sooner blame your chunking.

In `src/embedding.py` this is the difference between `embed_passages` (no prefix)
and `embed_query` (prefix). The two functions exist separately specifically so
the asymmetry is impossible to forget.

### Generalise this

The lesson isn't about BGE. It's that **embedding models are trained artifacts
with usage contracts, and the contract is not enforced at runtime.** Every family
has its own convention:

| Family | Query prefix | Passage prefix |
|---|---|---|
| BGE | `Represent this sentence for searching relevant passages: ` | none |
| E5 | `query: ` | `passage: ` |
| Nomic | `search_query: ` | `search_document: ` |
| OpenAI `text-embedding-3-*` | none | none |
| Voyage | set via an `input_type` parameter | set via `input_type` |

Read the model card. Violating the contract degrades quality silently in every
case.

## Why this project uses bge-small-en-v1.5

| Property | Value |
|---|---|
| Dimensions | 384 |
| Size on disk | ~133 MB |
| Max input | 512 tokens |
| Cost | free, runs locally on CPU |

Chosen over the more common `all-MiniLM-L6-v2` for a specific reason: **MiniLM is
trained for symmetric similarity** (is sentence A like sentence B?), while
retrieval is inherently **asymmetric** — a short question against a long passage.
BGE is trained on that objective directly and is measurably better at it.

It runs on CPU here. On this hardware, embedding all 53 chunks takes about 2.7
seconds. GPU would help at corpus sizes in the hundreds of thousands, not here.

## Normalisation

`embed_passages` and `embed_query` both pass `normalize_embeddings=True`, scaling
every vector to length 1.

This isn't cosmetic. For unit vectors, cosine similarity reduces to a plain dot
product:

$$\cos\theta = \frac{a \cdot b}{|a||b|} = a \cdot b \quad\text{when } |a| = |b| = 1$$

That's what lets the entire search in [[04 - The Vector Store Is One Matrix Multiply]]
be a single matrix multiply instead of a per-row cosine computation.

## What embeddings cannot do

This matters more than the capabilities, and it's where most RAG
misunderstandings live.

**They cannot judge whether an answer is present.** An embedding of a passage is
computed *before any question exists*. It's a summary of what the passage is
about. "This text is on the right topic but doesn't contain the specific fact
asked for" is a judgement about a question–passage *pair*, and the passage vector
never saw the question. This is exactly why
[[Similarity Thresholds Do Not Separate]] — and it's not a tuning problem, it's
structural.

**They blur rare tokens.** A 384-dimensional average over a whole passage
dilutes a single rare identifier like `stl_` or `QUILL_PG_POOL_SIZE`. This is
precisely where keyword search wins, and the reason for
[[05 - Dense vs Lexical vs Hybrid]].

**Their similarity scores are not calibrated.** A cosine of 0.65 means nothing in
absolute terms. Useful text-embedding scores cluster in a narrow band — on this
corpus, roughly 0.48 to 0.84 — and the band shifts with the model. Any threshold
you pick is tuned to one specific model on one specific corpus, and is invalid
the moment either changes. That's why `store.py` refuses to load an index built
with a different embedding model: vectors from different models aren't "less
comparable," they're meaningless together.

## Things to try

- Delete `BGE_QUERY_PREFIX` from `config.py` and re-run
  `scripts.evaluate --retrieval-only`. Observe the degradation and note how
  ordinary the output still looks.
- Swap `EMBEDDING_MODEL` to `sentence-transformers/all-MiniLM-L6-v2`, rebuild,
  and re-measure. Note that `MIN_SIMILARITY` is now wrong — MiniLM's score
  distribution is different.

---
Next: [[04 - The Vector Store Is One Matrix Multiply]]
