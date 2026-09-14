---
tags: [concept, context, cost]
---

# 06 — Context Is Not Free

## The measured exchange rate

From the eval run on this corpus:

| | Baseline | RAG |
|---|---|---|
| Mean prompt tokens | 54 | 1,234 |
| Correct answers | 2/14 | 13/14 |

RAG costs **~23x the prompt tokens**. It buys a jump from 14% to 93% correct.

On this workload that trade is obviously worth taking. The point of writing it
down is that it *is* a trade, with an exchange rate you can measure — and on a
different workload the same arithmetic gives a different answer.

Three things you pay:

**Tokens.** Direct cost on a metered API. On a local model, it's memory and time.

**Latency.** More prompt tokens means more prefill. Modest here; significant at
top_k=20 with large chunks.

**Attention.** The expensive one, and the one that isn't obvious.

## Why more retrieved chunks is not better

The intuition "retrieve more, give the model more to work with" is wrong, and
understanding why is the most practically useful idea in this note.

**Irrelevant context actively degrades answers.** A model treats retrieved text
as authoritative — that's what the grounding prompt told it to do
([[07 - The Grounding Prompt Does More Than You Think]]). Hand it a chunk that
looks topically relevant but doesn't contain the answer, and it will reason from
that chunk anyway, because you instructed it to trust the context over its
priors.

This is *context stuffing*, and it's a genuine failure mode rather than just
waste. Retrieving 20 chunks where 3 are relevant doesn't give the model "3 good
chunks plus some noise" — it gives it 17 opportunities to anchor on the wrong
thing.

There's a real example in this project's eval set. Question q13 asks *"How many
engineers work on the Ledger team and what are their names?"* The corpus never
says. But it does contain several real names — Priya Raghunathan, Wen Chen,
Tomas Lindqvist, Ravi Menon — in entirely different roles. A retriever returning
those chunks hands the model everything it needs to construct a confident, wrong
roster. The names are right there, the question asks for names, and the prompt
said to trust the context.

**Position matters too.** Attention across a long context is uneven; the
beginning is attended to most reliably, and material in the middle of a long
context is measurably more likely to be overlooked. That's why
`build_context_block` orders chunks **most relevant first** rather than by
document order.

## Why this project uses top_k = 5

Small enough that most retrieved chunks are genuinely relevant, large enough for
multi-hop questions needing facts from two documents.

Question q06 — *"Why is the event bus retention period set to 30 days
specifically?"* — is the one that sets the floor. The 30-day figure is in
ADR-014; the reason it must sit inside 90 days is in DATA-005. **Neither document
answers it alone.** At top_k=3 this question tends to retrieve only ADR-014 and
gets a partial answer.

That's the shape of the tradeoff: too low and multi-hop questions starve, too
high and you feed the model plausible distractors.

## Prompt structure follows from this

In `build_context_block`, three formatting decisions each address a specific
observed failure:

**Explicit delimiters and numbering.** `--- SOURCE 1 [OPS-002] ---`. Without a
clear boundary the model blends two documents into a single confident claim that
neither document makes.

**Citation markers inline.** Putting `[OPS-002]` in the text gives the model a
token it can copy. Asking for citations *without* supplying a handle produces
invented references — the model writes "[source 3]" for a source that doesn't
exist. A citation format the model must construct is a citation format it will
hallucinate.

**Question after context, not before.** The long stable context sits at the
front where prefix caching can reuse it across queries, and the instruction to
act on sits closest to where generation begins.

## The `num_ctx` trap

This one is specific to Ollama and cost real debugging time to find:

> **Ollama defaults `num_ctx` to 4096 regardless of what the model supports, and
> silently truncates from the *start* of the prompt.**

The start of the prompt is where the system message lives. So an over-long prompt
doesn't error — it quietly removes your grounding instructions and keeps the
context. The symptom is a model that ignores rules you can see in your own code,
for no apparent reason.

`config.OLLAMA_NUM_CTX = 16384` sets it explicitly. Anything that silently
discards part of your prompt belongs on a list of things to verify before
debugging anything else.

## Scaling the arithmetic

On a metered API, `prompt_tokens × price` per query. At 1,234 tokens and
Claude Opus 5 input pricing of $5/MTok, that's about **$0.006 per query** of
retrieval overhead — roughly $6 per thousand queries.

Levers when that matters:

- **Prompt caching.** The retrieved context changes per query, but a large stable
  system prompt in front of it can be cached. Structure the prompt so the stable
  part comes first.
- **Reranking.** Retrieve 20 candidates with a cheap method, rerank with a
  cross-encoder, pass the top 3. More compute, fewer tokens to the expensive
  model, and better precision than retrieving 3 directly — a cross-encoder reads
  the query and passage *together*, which is exactly the capability a bi-encoder
  lacks ([[03 - Embeddings and the Query-Passage Asymmetry]]).
- **Smaller chunks.** More precise retrieval, fewer wasted tokens — at the cost
  of severing facts ([[02 - Why Chunking Decides Everything]]).

## Things to try

- Run `scripts.evaluate --top-k 20` and compare accuracy and token cost against
  the k=5 baseline. Check specifically whether q13 starts inventing a roster.
- Run `--top-k 2` and watch q06 and q07 (the multi-hop questions) degrade.
- Set `OLLAMA_NUM_CTX = 2048`, run `scripts.ask --show-prompt`, and watch the
  model ignore instructions that are visibly present in the code.

---
Next: [[07 - The Grounding Prompt Does More Than You Think]]
