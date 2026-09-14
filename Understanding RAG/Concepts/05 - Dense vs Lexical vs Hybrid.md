---
tags: [concept, retrieval]
---

# 05 — Dense vs Lexical vs Hybrid

## The misconception

The most common wrong belief about RAG is that dense embedding search is simply
the better technology, and keyword search is what we used before we had it.

That isn't what the evidence shows. They fail in **different, complementary
places**, and a system running only one of them loses a predictable category of
query.

## How each one fails

**Dense retrieval** understands meaning and blurs specifics.

It knows "the thing that generates manifests" relates to Quill without either
phrase appearing in the other. But it's *worse* than keyword search at finding
the exact string `stl_` or `QUILL_PG_POOL_SIZE`, because a rare token gets
averaged away in a 384-dimensional summary of a whole passage. Rare identifiers
are exactly the tokens that carry the most information and exactly the ones
averaging destroys.

**Lexical retrieval (BM25)** matches exact terms and weights rare ones heavily.

It nails identifiers, error codes, config keys, proper nouns. It scores **zero**
on a query sharing no vocabulary with the passage, no matter how obviously
related the two are to a human.

BM25 scores a document by how many query terms it contains, weighted by term
rarity across the corpus (a match on "Vantage" is worth far more than a match on
"the"), dampened by document length so long documents don't win by surface area
alone.

## The split, visible in this corpus

- *"What is the ULID prefix used for settlement identifiers?"* — a **BM25**
  question. `stl_` appears once in the corpus and has no semantic neighbourhood.
- *"If the Vantage API goes down, what happens to shipments?"* — a **dense**
  question. The answer discusses circuit breakers and queuing without restating
  the question's framing.
- *"Is Atlas a database?"* — measured at **dense 1.00, lexical 0.50**. The word
  "database" pulls BM25 toward the wrong documents; dense retrieval understands
  the question is about what Atlas *is*.

## Hybrid: fusing by rank, not by score

`Retriever.hybrid()` runs both and combines them with **Reciprocal Rank Fusion**:

$$\text{RRF}(d) = \sum_{s \in \text{strategies}} \frac{1}{k + \text{rank}_s(d)}$$

with `k = 60` from the original Cormack et al. paper.

### Why rank and not score

This is the part worth understanding.

Cosine similarity lives in `[-1, 1]`. BM25 is **unbounded and corpus-dependent** —
a BM25 score of 8.0 means nothing on its own. There is no principled way to add
them.

Any normalisation you invent (min-max, z-score) is computed over the particular
result set and will swing wildly between queries: a query where the best BM25
score is 12 and one where it's 2 produce completely different normalised scales,
so the same underlying match quality maps to different numbers.

Ranks are directly comparable *by construction*. "Third best according to this
strategy" means the same thing regardless of strategy, corpus, or query.

### What k controls

`k = 60` makes rank 1 score `1/61` and rank 2 score `1/62` — very close. Top
ranks aren't sharply favoured over near-top ranks.

That's the behaviour we want: a document ranked highly by **both** strategies
beats one ranked first by only one. Agreement between independent methods is
strong evidence. A small `k` would let a single strategy's top hit dominate,
discarding exactly the signal fusion exists to capture.

### Over-fetching

We fetch `top_k * 3` from each strategy before fusing. A chunk sitting at rank 8
in both strategies is often a better answer than one at rank 1 in a single
strategy — but it can't win the fusion if it was never retrieved in the first
place.

## The threshold exception

In `Retriever.retrieve()`, hybrid results are filtered by cosine similarity —
**except** for chunks that BM25 found:

```python
if cosine < threshold and "lexical" not in srcs:
    continue
```

That exception is the whole point of hybrid retrieval. A chunk with a strong
exact-term match but a low cosine is precisely the case where the embedding
blurred away the vocabulary that mattered. Filtering it on cosine would discard
the results BM25 was added to provide.

Note also that the threshold is always applied to the **cosine**, never to the
fused RRF score. An RRF score has no absolute meaning — it depends on how many
strategies found the chunk and where — so thresholding it would be arbitrary.

## Measured results

From `scripts.evaluate --compare-strategies` on this corpus:

| Strategy | Mean recall |
|---|---|
| Dense | 0.79 |
| Lexical | 0.75 |
| Hybrid | 0.79 |

**Read this honestly: hybrid did not beat dense here.** Two reasons, and both are
properties of the test rather than of hybrid retrieval:

1. The corpus is 53 chunks across 8 well-separated topics. Retrieval is easy —
   dense alone scores 1.00 on every answerable question. There's no headroom for
   hybrid to demonstrate anything.
2. The eval set has only one question (q11) where the strategies actually
   diverge.

The place hybrid earns its keep is a large corpus with many near-duplicate
documents and heavy identifier vocabulary — which is what a real codebase or
runbook set looks like at scale. This corpus is too small and too clean to show
it. That's worth stating plainly rather than quietly reporting the tie as a win:
**a benchmark that can't distinguish two approaches hasn't shown they're
equivalent, it's shown the benchmark is too easy.**

## Things to try

- Add 200 documents of near-duplicate runbooks and re-run the sweep. Watch the
  strategies separate.
- Write five questions built around exact identifiers (`shp_`, `MER-3341`,
  `sibling_shipment_id`) and watch lexical beat dense.
- Set `RRF_K = 1` and see top-1 results dominate the fusion.

---
Next: [[06 - Context Is Not Free]]
