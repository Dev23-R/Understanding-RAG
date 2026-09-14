# Start Here

This vault documents a working RAG system built from scratch in `D:\RAG Project`,
and more importantly *why* each part of it is built the way it is.

The goal is not to have a RAG system. The goal is to understand what retrieval
does to a model's output well enough to reason about it in new situations —
particularly the situation you care about: giving an agentic tool the strongest
possible context.

## The one-paragraph version

A language model knows what was in its training data. It does not know your
company's runbooks, your codebase's conventions, or anything that happened after
its cutoff. Asked about those, it does not say "I don't know" — it produces
something fluent and wrong. RAG fixes this by finding relevant text at query time
and putting it in the prompt. The model then reads rather than recalls. That is
the entire idea; everything else is engineering.

## Read in this order

**Concepts** — the reasoning behind each stage of the pipeline.

1. [[01 - What RAG Actually Is]]
2. [[02 - Why Chunking Decides Everything]]
3. [[03 - Embeddings and the Query-Passage Asymmetry]]
4. [[04 - The Vector Store Is One Matrix Multiply]]
5. [[05 - Dense vs Lexical vs Hybrid]]
6. [[06 - Context Is Not Free]]
7. [[07 - The Grounding Prompt Does More Than You Think]]
8. [[08 - Measuring Whether Any Of This Worked]]
9. [[09 - RAG as Agentic Context Engineering]]

**Findings** — things this project measured, including two that contradicted
what I expected going in.

- [[The Atlas Hallucination]] — the clearest single demonstration of why RAG matters
- [[Similarity Thresholds Do Not Separate]] — a widely-repeated technique that fails under measurement
- [[Eval Results]] — the numbers

**Reference**

- [[Project Map]] — what each file does
- [[Commands]] — how to run everything
- [[Meridian Corpus]] — the test corpus and why it's fictional

## The honest framing

RAG is often sold as "gives the model your data." A more useful framing is that
RAG **changes what the model is doing** — from recall to reading comprehension.
Models are much better at reading comprehension than they are at recall, and
their failure modes when reading are far more visible than their failure modes
when recalling.

That shift is the actual value, and it's why [[The Atlas Hallucination]] is worth
studying closely: the baseline answer there was *confident, detailed, internally
consistent, and entirely invented*. Nothing about its surface told you it was
wrong.
