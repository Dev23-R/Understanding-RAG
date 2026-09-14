---
tags: [finding, retrieval, negative-result]
---

# Similarity Thresholds Do Not Separate

A negative result, and the most useful thing this project measured — because the
technique it disproves is advice you'll find repeated everywhere, it sounds
obviously correct, and it fails quietly.

Reproduce with: `.venv\Scripts\python.exe -m scripts.threshold_analysis`

## The claim being tested

> Set a minimum similarity score. If the best retrieved chunk scores below it,
> the question is out of scope — return "I don't know" instead of hallucinating.

Intuitive, cheap, and widely recommended. It does not work.

## The measurement

Top-1 cosine similarity for every eval question, sorted:

| Question | Category | Top-1 |
|---|---|---:|
| q04 Which env var controls Quill's pool size? | lookup | 0.835 |
| q05 Can I deploy on a Friday? | lookup | 0.826 |
| q06 Why is bus retention 30 days? | multihop | 0.811 |
| q07 Why two regional stacks? | multihop | 0.779 |
| q02 ULID prefix for settlements? | lookup | 0.745 |
| q08 Why is the Atlas outage still possible? | multihop | 0.739 |
| q03 How long is the soak period? | lookup | 0.730 |
| q01 Max Atlas replicas? | lookup | 0.712 |
| **q12 Parental leave policy?** | **absent** | **0.688** |
| q09 What if Vantage goes down? | multihop | 0.685 |
| q11 Is Atlas a database? | collision | 0.664 |
| q14 Vantage SLA? | lookup | 0.657 |
| **q10 What language is Sentry written in?** | **lookup** | **0.615** |
| q13 Ledger team headcount? | absent | 0.537 |

**q12 is unanswerable and scores 0.688. q10 is answerable and scores 0.615.**

The unanswerable question ranks higher than the answerable one. There is no
threshold that separates them.

## The cost of trying anyway

| Threshold | Answerable rejected | Unanswerable rejected |
|---:|---:|---:|
| 0.30 | 0/12 | 0/2 |
| 0.50 | 0/12 | 0/2 |
| 0.60 | 0/12 | 1/2 |
| 0.65 | 1/12 | 1/2 |
| 0.70 | **4/12** | 2/2 |
| 0.75 | **8/12** | 2/2 |

To reject both unanswerable questions you need 0.70 — which throws away **a third
of the questions the corpus answers perfectly well.**

## Why it fails — structural, not a tuning problem

This is the part worth internalising, because it generalises far beyond
thresholds.

**A passage embedding is computed before any question exists.**

It encodes what the passage is *about*. It cannot encode "this passage is on the
right topic but does not contain the specific fact someone will later ask for",
because that is a property of a **question–passage pair**, and the passage vector
never saw a question.

And q12's high score is *correct behaviour*, not an error. "What is Meridian's
**parental leave policy**?" genuinely is close to "Meridian **Data Retention and
Residency Policy**" — same organisation, same document genre, shared vocabulary,
same register. The embedding is doing exactly what it was trained to do. Topical
relatedness is simply not the quantity we need.

No amount of tuning fixes a metric that measures the wrong thing.

## What actually works

The component that can read the question and the passage **together** is the
generating model. So the refusal has to be its job, requested explicitly:

```
1. If the context does not contain the answer, say "The provided
   documentation does not cover this." Do not fill the gap from
   general knowledge.
```

Measured result: `absent` questions go **0/2 baseline → 2/2 with RAG**. The
threshold contributed nothing to that; `MIN_SIMILARITY = 0.30` rejects nothing on
this corpus.

## So why keep a threshold at all

It's a filter for genuine garbage — an empty query, a language the corpus doesn't
contain, a question about an unrelated domain scoring 0.15. That's worth having.

It is **not** a hallucination defence, and treating it as one is a common and
expensive mistake: you ship a system believing it has a safety net, and the net
isn't attached to anything.

## The generalisation

This is the **bi-encoder limitation**, and it's the single most important
structural fact about embedding retrieval.

- A **bi-encoder** embeds query and document *separately*. Fast — you precompute
  every document vector once and search is one matrix multiply. But the two sides
  never meet, so the score is topical relatedness at best.
- A **cross-encoder** processes query and document *together* and outputs a
  relevance score. Far more accurate. Far more expensive — no precomputation
  possible, one forward pass per (query, document) pair.

Standard production architecture follows directly: **bi-encoder to retrieve 50
candidates cheaply, cross-encoder to rerank down to 5.** That's not a performance
optimisation, it's a correctness one — the reranker is the first component in the
pipeline that can tell "right topic" from "right answer".

In this project, the generating model plays the cross-encoder role: it reads the
question and the retrieved chunks together and makes the judgement the embedding
couldn't.

For an agent, the same logic applies to deciding whether a search actually
answered the question — see [[09 - RAG as Agentic Context Engineering]]. A
similarity score can't tell it. Reading the results can.

Related: [[03 - Embeddings and the Query-Passage Asymmetry]] ·
[[07 - The Grounding Prompt Does More Than You Think]] · [[Eval Results]]
