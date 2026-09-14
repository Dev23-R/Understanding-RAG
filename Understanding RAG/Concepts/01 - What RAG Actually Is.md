---
tags: [concept, foundations]
---

# 01 — What RAG Actually Is

## The problem it solves

A language model's knowledge is frozen into its weights during training. That
knowledge has three properties that cause trouble:

1. **It has a cutoff.** Anything after it is invisible.
2. **It excludes anything private.** Your runbooks, your codebase, your Slack.
3. **It is lossy and unattributed.** The model cannot tell you where it learned
   something, or how confident it should be.

Property 3 is the dangerous one. A model asked about something it doesn't know
does not reliably say so. It produces the most plausible continuation, which for
a question about a system it's never seen means *inventing a system that sounds
right*. See [[The Atlas Hallucination]] for this happening in this project, in
detail, with a confident wrong answer that a non-expert reader would accept.

## The mechanism

RAG inserts a retrieval step before generation:

```
question
   ↓
[retrieve]  → find text likely to contain the answer
   ↓
[augment]   → put that text in the prompt
   ↓
[generate]  → model answers from what's in front of it
```

That's it. The "R" is a search engine, the "A" is string concatenation, and the
"G" is a normal model call.

## Why it works better than it sounds like it should

The interesting part isn't that the model gets new facts. It's that **the task
changes**.

Without retrieval, you're asking: *what do you remember about X?* That's recall
from a lossy compressed store, and the model has no reliable signal for whether
its recall is grounded or confabulated.

With retrieval, you're asking: *here is a document; what does it say about X?*
That's reading comprehension. Models are substantially better at this, and
critically, **their failures become visible**. A model misreading a document in
front of you is checkable. A model misremembering something is not.

This reframing is the thing to carry into [[09 - RAG as Agentic Context Engineering]].

## What RAG is not

**It is not fine-tuning.** Fine-tuning adjusts weights to change behavior,
style, or format. It is a poor way to install facts: facts you fine-tune in are
still unattributed, still lossy, and updating them means retraining. Retrieval
updates by editing a markdown file.

**It is not a memory system.** Vanilla RAG is stateless; each query retrieves
independently with no notion of what was retrieved before or what the user has
already been told.

**It is not a guarantee of correctness.** It relocates the failure. The model can
now be wrong because retrieval returned the wrong chunk, because the right chunk
was split in half ([[02 - Why Chunking Decides Everything]]), because the
retrieved text was stuffed alongside three irrelevant chunks
([[06 - Context Is Not Free]]), or because the model ignored the context in
favour of its priors ([[07 - The Grounding Prompt Does More Than You Think]]).

Each of those is a *different bug with a different fix*, which is why
[[08 - Measuring Whether Any Of This Worked]] insists on scoring retrieval and
generation separately.

## The pipeline, concretely

Indexing, done once per corpus change:

| Stage | Module | Note |
|---|---|---|
| Load documents | `src/corpus.py` | Parse frontmatter, extract titles |
| Split into chunks | `src/chunking.py` | Structure-aware — [[02 - Why Chunking Decides Everything]] |
| Embed each chunk | `src/embedding.py` | Text → 384-dim vector |
| Store | `src/store.py` | A numpy matrix — [[04 - The Vector Store Is One Matrix Multiply]] |

Querying, done per question:

| Stage | Module | Note |
|---|---|---|
| Embed the question | `src/embedding.py` | With a query prefix — [[03 - Embeddings and the Query-Passage Asymmetry]] |
| Search | `src/retrieval.py` | Dense + lexical fused — [[05 - Dense vs Lexical vs Hybrid]] |
| Build the prompt | `src/generation.py` | Delimiters, citations, ordering |
| Generate | `src/generation.py` | Local model via Ollama |

## Why this project's corpus is fictional

Every fact in `corpus/` is invented — see [[Meridian Corpus]]. This is
deliberate and it is what makes the experiment clean: since the model provably
cannot know any of it, any correct answer must have come from retrieval. With a
real-world corpus you can never fully separate "retrieval worked" from "the model
already knew this."
