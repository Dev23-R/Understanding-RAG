---
tags: [finding, hallucination]
---

# The Atlas Hallucination

The clearest single demonstration this project produced. Worth studying closely
because the failure is *not* obvious from the output — which is the entire point.

## Setup

Same model (`qwen3:8b`), same question, same decoding settings. The only variable
is whether retrieved context is in the prompt.

> **Q: What should I do when the AtlasQueueDepthGrowing alert fires, and what is
> the maximum replica count?**

## Without retrieval

> When the **AtlasQueueDepthGrowing** alert fires, it indicates the queue depth
> (number of pending operations) in your sharded cluster is increasing,
> potentially signaling performance bottlenecks. Take these steps:
>
> 1. **Check metrics**: Use MongoDB Atlas metrics to identify if the queue depth
>    is due to high write load, balancer activity, or shard imbalance.
> 2. **Monitor balancer**: Ensure the balancer is not actively migrating chunks…
> 3. **Scale horizontally**: Add more shards or increase replica set sizes…
>
> **Maximum replica count**:
> - A MongoDB replica set can have **up to 16 members** (including the primary).
> - The maximum number of **secondaries** is **15**…

*59 prompt tokens, 1,021 completion tokens, 75.9s*

## With retrieval

> When the `AtlasQueueDepthGrowing` alert fires, scale Atlas replicas up first
> using the command: `kubectl -n meridian scale deploy/atlas --replicas=12`
> [OPS-002]. The maximum replica count is **16**, as exceeding this would exceed
> PostGIS's connection limit of 200 connections [OPS-002].

*1,143 prompt tokens, 326 completion tokens, 4.4s*

## What actually happened

The model saw "Atlas" and pattern-matched to **MongoDB Atlas**, the widely-known
managed database product. It then generated a complete, coherent, professionally
formatted incident procedure for a system that has nothing to do with the
question.

Our Atlas is a Go geospatial hub capacity service backed by PostGIS.

Every specific in the baseline answer is wrong: there is no sharded cluster, no
balancer, no chunk migration, and "add more shards" is not a thing you can do.

## The part that should genuinely unsettle you

**The baseline says the maximum replica count is 16. That is the correct number.**

The real answer is also 16 — because Atlas holds one PostGIS connection per
replica and the PostGIS instance caps at 200 connections shared across all
consumers.

The baseline got it right for a completely unrelated reason: 16 is the member
limit of a MongoDB replica set.

So:

- A reader spot-checking the number would **confirm it** and conclude the answer
  is sound.
- Anyone reasoning *onward* from the stated rationale — "it's a replica set
  member limit, so it's a hard protocol constraint, so 16 is safe under any
  circumstances" — would be reasoning from fiction.
- The actual constraint is a shared connection pool. If someone raised PostGIS's
  cap, or another service started consuming connections, the correct limit
  changes. Under the MongoDB story it never would.

**A right answer for a wrong reason is still a failure**, because the reason is
what you reason from next.

This is the deepest argument for retrieval. The problem isn't that ungrounded
models are wrong often enough to notice. It's that when they're wrong, nothing on
the surface distinguishes it from being right — not confidence, not detail, not
internal consistency, and as here, not even the answer itself.

## Secondary observations

**The grounded answer is shorter and faster.** 326 completion tokens versus 1,021;
4.4s versus 75.9s. The baseline had to *reason* its way to a plausible-sounding
answer. With the fact in the prompt there's nothing to reason about. Retrieval
substituted for reasoning effort — see
[[07 - The Grounding Prompt Does More Than You Think]].

**The cost was 1,084 extra prompt tokens** — a 19x increase for this question.
That's the exchange rate ([[06 - Context Is Not Free]]).

**Retrieval was clean.** Top hit was the exact runbook section at cosine 0.823,
found by both dense and lexical search.

## The name collision was deliberate

The corpus names services Atlas, Sentry, Beacon, Hermes, Ledger, and Quill —
every one colliding with a well-known product (MongoDB Atlas, Sentry.io, and so
on). Real organisations name things this way constantly, and strong priors about
the wrong referent are exactly what grounding has to overcome.

`corpus/glossary.md` calls the collisions out explicitly, which is also realistic
— and gives retrieval something concrete to surface.

Related: [[01 - What RAG Actually Is]] · [[Eval Results]]
