---
tags: [concept, chunking]
---

# 02 — Why Chunking Decides Everything

Chunking gets the least attention of any RAG stage and has the most leverage.
The reason is simple and absolute:

> **Retrieval can only ever return a chunk you created.**

If a fact is split across two chunks, no embedding model, no reranker, and no
amount of prompt engineering can recover it. The ceiling on your whole system is
set here, before any of the interesting machinery runs.

## Why not just split every 1000 characters

Fixed-size splitting is the default in most tutorials because it's one line of
code. It's also actively destructive, and this corpus shows why concretely.

`corpus/oncall-runbook.md` documents four alerts. Each has a name, a
description, and — critically — a **Mitigation** section saying what to do.

Split at a fixed 1000 characters, the `SentryVantageTimeout` entry breaks
mid-section. The sentence *"do not disable the circuit breaker to let traffic
through, because unscreened shipments crossing a border is a regulatory
violation"* lands in a different chunk from the alert name.

Now a query like "what do I do when Vantage times out?" retrieves the chunk
containing the alert name — and that chunk **omits the single most important
instruction in the document**. The system confidently returns a partial
procedure. The failure is invisible: the answer looks complete.

## What this project does instead

Split on **document structure** — markdown headings.

A heading is the author telling you where one topic ends and the next begins.
That's free, high-quality segmentation signal, and fixed-size splitting throws it
away. See `_split_into_sections` in `src/chunking.py`.

Three refinements on top:

**Track the full heading path, not just the nearest heading.** A chunk whose
nearest heading is `Mitigation` is useless out of context. `Meridian On-Call
Runbook > Common alerts > AtlasQueueDepthGrowing > Mitigation` tells you exactly
what you're looking at.

**Merge chunks that are too small.** A heading with one line under it embeds
badly — with so few tokens, a single shared common word can dominate the
similarity score and surface it for unrelated queries. `CHUNK_MIN_TOKENS = 48`.

**Split sections that are too large.** Two reasons, and the second is the one
people miss:

- The embedding model has a hard 512-token input limit and **truncates silently**
  past it. You get a valid-looking vector back that simply ignored the tail of
  your chunk. No error, no warning.
- Even under the limit, a long chunk produces a *vague* embedding. Averaging
  many topics into one 384-dimensional vector puts it close to nothing in
  particular. A chunk about six things matches queries about none of them well.

## The context header — cheapest large win available

Every chunk in this project is prefixed with its document title and heading path
before being embedded:

```
Meridian On-Call Runbook > Common alerts > QuillPoolExhausted

Fires when Quill's Postgres connection pool has zero free connections
for 2 minutes. Nearly always month-end manifest generation.
Mitigation: Raise the pool size via the QUILL_PG_POOL_SIZE
environment variable -- it is safe up to 30.
```

Why this matters: **chunk text is written assuming the reader has the surrounding
document.** The body above never says the word "alert." It never says Quill is
the document generation service. Someone asking *"what do I do when the document
service runs out of database connections?"* uses none of the vocabulary actually
present in the chunk.

The header injects that missing vocabulary into the embedded text, so the chunk
becomes findable by the words people actually search with.

This technique is sometimes called *contextual retrieval*. More elaborate
versions use an LLM to write a custom one-sentence summary per chunk at index
time. That's better and costs one model call per chunk. The heading-path version
costs nothing and captures most of the benefit.

We store the prefixed form in `chunk.text` (embedded, shown to the model) and the
clean form in `chunk.body` (shown to humans), so the synthetic prefix never
clutters a displayed excerpt.

## Overlap

Adjacent chunks share `CHUNK_OVERLAP_TOKENS = 64`. This exists so a fact spanning
a boundary isn't severed — without it, a sentence straddling the split is in
neither chunk in a retrievable form.

The cost is index size and occasional duplicate results. Overlap is a patch over
bad boundaries, not a substitute for good ones; structure-aware splitting means
we need much less of it than a fixed-size splitter would.

## Sizing in tokens, never characters

`CHUNK_TARGET_TOKENS = 320`, measured with **the embedding model's own
tokenizer** (`embedding.count_tokens`).

Not a word count, not `len(text) // 4`. The 512-token limit is enforced in
tokens, and silently. Budgeting in characters means your limit is approximate in
exactly the situation where being wrong is invisible.

Target is 320 rather than the full 512 because the context header costs tokens
too, and that context is worth more than the extra body text it displaces.

## What this corpus actually produced

```
53 chunks across 8 documents
min 35 · p50 156 · p90 294 · max 352 tokens
```

Max 352 against a 512 limit — nothing truncated. A p50 of 156 is on the small
side, which suits a reference corpus of short factual sections; a corpus of
long-form prose would sit higher.

## A warning about tokenizer warnings

Building the index emits:

```
Token indices sequence length is longer than the specified maximum
sequence length for this model (843 > 512)
```

This looks alarming and is **a false alarm**. It fires because `count_tokens`
runs the tokenizer over a whole 843-token document *section* in order to decide
how to split it. That string is never embedded. HuggingFace can't distinguish
measuring from encoding, so it warns anyway.

It's suppressed with `verbose=False` in `src/embedding.py`, with a comment
explaining why. Worth doing deliberately: a scary-but-meaningless warning is how
you learn to ignore your own logs, and the same message from `embed_passages`
*would* mean real silent data loss.

## Things to try

- Set `CHUNK_TARGET_TOKENS = 1000` and re-run `scripts.evaluate --retrieval-only`.
  Watch multi-hop recall move.
- Set it to `80`. Facts get severed; single-fact lookups may improve while
  anything needing context degrades.
- Delete the context header (the `text = f"{header}\n\n{piece}"` line) and
  re-measure. This is the cheapest way to see how much it was buying.

---
Next: [[03 - Embeddings and the Query-Passage Asymmetry]]
