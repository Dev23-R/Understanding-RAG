---
tags: [concept, evaluation]
---

# 08 — Measuring Whether Any Of This Worked

Without measurement, every RAG change is a vibe. You tweak chunk size, the
answers feel better, you keep it. Three changes later something is worse and you
have no idea which one did it.

## Score the two halves separately

RAG has two failure surfaces and they need different fixes:

| Surface | Question | Fix lives in |
|---|---|---|
| **Retrieval** | Did the right documents come back? | chunking, embeddings, search |
| **Generation** | Did the model use them correctly? | the prompt, top_k, the model |

A question can fail retrieval and still be answered correctly by luck, or
retrieve perfectly and be answered badly. **A single end-to-end score cannot tell
you which half to fix**, which makes it nearly useless for iterating.

So `evals/questions.yaml` carries both kinds of ground truth:

```yaml
- id: q06
  category: multihop
  question: Why is the event bus retention period set to 30 days specifically?
  expected_docs: [ADR-014, DATA-005]     # grades RETRIEVAL
  must_include: ["90"]                    # grades GENERATION
```

## Why recall, not F1

`grade_retrieval` measures **recall** of expected documents.

Not precision, not F1, because the costs aren't symmetric here. A missing
document means a wrong answer. An extra document means some wasted tokens and a
modest risk of distraction ([[06 - Context Is Not Free]]). Collapsing those into
one number hides the thing you actually care about.

An `absent` question expects zero documents, so recall is defined as 1.0 when
nothing is retrieved — finding nothing correctly is a success, and dividing by an
empty set is undefined.

## Question categories

Deliberately mixed, because **RAG's benefit is not uniform** and the aggregate
number hides where it comes from:

| Category | Tests |
|---|---|
| `lookup` | One fact, one document |
| `multihop` | Combining two or more documents |
| `collision` | Terms colliding with strong model priors (Atlas, Sentry) |
| `absent` | Information genuinely not in the corpus — refusal expected |

The `absent` category is the one most eval sets omit and the one that catches the
most dangerous failures. A system scoring 100% on questions it can answer, while
confidently inventing answers to questions it can't, is worse than useless in
production — it's actively misleading, and it passes the eval.

## Substring grading: what it buys and what it costs

Grading is deterministic substring matching, not an LLM judge. That's a
deliberate limitation with a real justification:

- An LLM judge introduces a **second model whose own failures you'd have to
  debug**. When the judge disagrees with you, is the system wrong or the judge?
- On exact ground truth — a specific number, a specific env var name — substring
  matching is **sufficient and unarguable**.
- It's free and instant, so you'll actually run it.

### Where it fails — demonstrated on itself

Question q11 (*"Is Atlas a database?"*) originally used
`must_not_include: ["MongoDB"]`, reasoning that a MongoDB mention indicates the
model fell for the name collision.

The grounded answer was **correct**:

> "Atlas is not a database... explicitly distinguished from MongoDB Atlas (which
> is not used by Meridian)"

and was **graded as a failure**, because it contains the string "MongoDB" — which
it contains because the glossary itself says *"Not to be confused with MongoDB
Atlas, which we do not use."*

**Substring matching has no concept of negation.** It cannot separate "Atlas IS
MongoDB Atlas" from "Atlas is NOT MongoDB Atlas."

The narrow fix: forbid the *assertion*, not the vocabulary —
`must_not_include: ["Atlas is a database", "Atlas is MongoDB"]`.

The general lesson: a cheap grader produces false failures, and **a false failure
you don't investigate is worse than no eval at all**, because it sends you
optimising against a bug in your ruler. Always read the failures before trusting
the number.

This is the single clearest argument for an LLM judge, which would handle
negation, paraphrase, and partial credit. The right time to add one is when
manual review of failures becomes the bottleneck.

## Persisting runs

Every run writes `evals/runs/<timestamp>-<strategy>-k<n>.json`, including the
full config that produced it:

```json
"config": {
  "strategy": "hybrid", "top_k": 5, "think": false,
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "generation_model": "qwen3:8b",
  "chunk_target_tokens": 320, "min_similarity": 0.3
}
```

A single score tells you nothing. **The delta after a config change tells you
everything.** Storing the config alongside the result is what makes a run from
three weeks ago interpretable.

## Guarding against fooling yourself

- **Write questions before tuning.** Questions written after you've seen the
  system's behaviour are questions your system already passes.
- **Include questions you expect to fail.** An eval you score 100% on has stopped
  measuring anything.
- **Watch for a benchmark that's too easy.** On this corpus dense, lexical and
  hybrid all score ~0.79 recall. That doesn't mean they're equivalent
  ([[05 - Dense vs Lexical vs Hybrid]]) — it means 53 well-separated chunks can't
  distinguish them. A benchmark that can't tell two approaches apart hasn't shown
  they're the same; it's shown the benchmark is too easy.
- **Fix a seed.** `OLLAMA_TEMPERATURE = 0.0` and `OLLAMA_SEED = 42`, so a
  difference between runs is a real difference and not sampling noise.

## Things to try

- Add an LLM judge as a second grader; measure how often it disagrees with
  substring matching, and who's right when it does.
- Add 10 harder questions and watch the strategy comparison separate.
- Re-run with `--think` and compare. Note where thinking helps (baseline) and
  where it doesn't (grounded) — see
  [[07 - The Grounding Prompt Does More Than You Think]].

---
Next: [[09 - RAG as Agentic Context Engineering]]
