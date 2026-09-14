---
tags: [concept, agents, context-engineering]
---

# 09 — RAG as Agentic Context Engineering

This is the note that connects the pipeline you just built to the thing you
actually want: giving an agentic tool the strongest possible context.

## The reframe

Classic RAG is a *question-answering* architecture: one question in, retrieve
once, answer once. That's what this project implements, and it's the right thing
to build first because every part of it is visible.

Agents are different in one structural way: **an agent decides what it needs to
know, and it decides repeatedly.**

| | Classic RAG | Agentic retrieval |
|---|---|---|
| Who forms the query | Your code, from the user's question | The model, from its current goal |
| How many retrievals | Exactly one | As many as the task needs |
| When | Before generation | Interleaved with reasoning and action |
| What's retrieved | Text chunks | Text, file contents, command output, API results |
| Failure recovery | None — one shot | Re-query, refine, try a different tool |

The shift is from *retrieval as a preprocessing step* to **retrieval as a tool
the model can call**.

## What carries over unchanged

Almost all of it. This is the useful part — the lessons you just measured are not
specific to the one-shot architecture:

**[[02 - Why Chunking Decides Everything]]** — An agent reading a 4,000-line file
faces the same problem as a retriever returning a chunk. What unit of information
comes back? A tool returning whole files burns context; one returning 20-line
fragments severs the thing being looked for. Same tradeoff, same reasoning.

**[[06 - Context Is Not Free]]** — This matters *more* for agents, not less. A
one-shot RAG call is 1,234 tokens and done. An agent accumulates every tool
result across every turn. Context management — what to keep, what to summarise,
what to drop — becomes the dominant engineering problem in long-running agents.

**[[07 - The Grounding Prompt Does More Than You Think]]** — Rule 1 (admit when
the answer isn't there) is what stops an agent inventing a file it never read.
Rule 3 (context beats priors) is what stops it applying general conventions to a
codebase with its own. Both are load-bearing.

**[[Similarity Thresholds Do Not Separate]]** — Directly applicable. An agent
deciding "did that search actually answer my question?" cannot use a similarity
score for the same structural reason: the judgement requires reading the query and
result together. The model has to make that call.

## What changes

**The model writes the query.** This is a large advantage, under-appreciated. A
user asks *"why is the deploy failing?"* — bad search query. An agent can decompose:
search for the error string, then the deploy config, then the recent changes. It
can also re-query when the first attempt returns nothing useful. One-shot RAG
cannot recover from a bad query; an agent can.

**Retrieval competes with other tools.** Semantic search is one option next to
grep, reading a file, running a test, calling an API. Different tools suit
different questions, and this maps directly onto
[[05 - Dense vs Lexical vs Hybrid]]: grep is lexical retrieval with perfect
precision and zero semantic understanding. *"Where is `QUILL_PG_POOL_SIZE`
set?"* is a grep question. *"How does this service handle backpressure?"* is a
semantic search question. An agent with both, and the judgement to choose, beats
one with either.

**Relevance is judged after retrieval, not before.** An agent reads what came
back and decides whether it helped. That's a cross-encoder-shaped judgement — the
model sees query and result together — and it's strictly more capable than any
threshold on a bi-encoder score.

## The practical implication

The highest-leverage thing you can do for an agentic tool is usually **not** a
better embedding model. It's the same set of things this project measured:

1. **Make the corpus good.** Retrieval cannot surface what isn't written down.
   An agent working against stale or absent documentation fails no matter how
   good the retriever is. This is the least glamorous and highest-impact lever.

2. **Make the retrievable unit the right size.** Both for what comes back and
   what it costs to include.

3. **Give the model the metadata to judge relevance.** The context header from
   [[02 - Why Chunking Decides Everything]] does this — file path, heading path,
   document title. An agent that can see *where* a result came from can decide
   whether to trust it, and can navigate from it.

4. **Instrument it.** [[08 - Measuring Whether Any Of This Worked]] applies
   unchanged. An agent whose retrieval quality you can't measure is an agent you
   can't improve.

## The honest limitation of what's built here

This project implements **one-shot retrieval with no feedback loop**. Turning it
into agentic retrieval means:

- Exposing `Retriever.retrieve()` as a **tool definition** the model can call
- Letting the model issue **multiple searches** per task, with different queries
- Returning **enough metadata** (source path, heading path, score) for the model
  to decide what to read next
- Adding **complementary tools** — read a file, list a directory, grep — because
  semantic search is the wrong instrument for a large class of questions

The retrieval core doesn't change. What changes is who calls it, how often, and
what happens to the result.

That's the natural next project, and everything in this vault is the
prerequisite: you can't reason about *when an agent should search* until you
understand what search does and how it fails.

---
Back to [[Start Here]]
