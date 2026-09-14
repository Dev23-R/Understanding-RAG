---
tags: [concept, prompting]
---

# 07 — The Grounding Prompt Does More Than You Think

Retrieval puts the right text in front of the model. The prompt decides whether
the model **uses** it, **trusts** it over its own priors, and **admits** when it
isn't there.

Those are three separate failure modes. Each rule in `GROUNDED_SYSTEM` addresses
one.

## The prompt

```
Answer using ONLY the context provided below. The context is
authoritative internal documentation.

Rules:
1. If the context does not contain the answer, say "The provided
   documentation does not cover this." Do not fill the gap from
   general knowledge.
2. Cite the source of each claim using the [DOC-ID] markers shown
   in the context.
3. If the context contradicts what you believe to be generally true,
   follow the context. This is a specific organisation with its own
   conventions.
4. Be concise and specific. Prefer exact values, commands, and names
   from the context over paraphrase.
5. Do not speculate about what the documentation "probably" means
   beyond what it states.
```

## Rule 1 — the refusal clause is the real hallucination defence

This is the most important line, and its importance is easy to miss because the
obvious candidate for this job is the similarity threshold.

It isn't. [[Similarity Thresholds Do Not Separate]] shows, with measurements from
this corpus, that no threshold value distinguishes answerable from unanswerable
questions. The unanswerable *"What is Meridian's parental leave policy?"* scores
**0.688** — higher than the perfectly answerable *"What language is Sentry
written in?"* at **0.615**.

The reason is structural. An embedding is computed before any question exists. It
encodes what a passage is *about*, not whether it contains a particular fact.
Judging "right topic, wrong fact" requires reading the question and the passage
**together** — and the only component in the pipeline that does that is the
generating model.

So the refusal has to be the model's job, and rule 1 is how you ask for it. The
measured result: `absent` questions go **0/2 baseline → 2/2 with RAG**.

Supplying the exact refusal string matters. "Say you don't know" produces varied
phrasings that are hard to grade and hard for downstream code to detect. A fixed
string is a detectable signal.

## Rule 3 — the priors-override clause

Without this rule, a model with a strong prior will quietly follow the prior even
with contradicting context right in front of it.

This corpus is built to test exactly that. **Sentry** here is a Rust customs
compliance service. Sentry.io is a very well-known error tracking product, and
the model has seen a great deal about it. Question q10 asks what language Sentry
is written in and what it does.

Baseline: **0/2** on collision questions. With RAG and rule 3: correct.

The framing *"This is a specific organisation with its own conventions"* does
real work. It gives the model a *reason* the context should win, rather than a
bare instruction. Models follow justified instructions more reliably than
unjustified ones.

## Rule 2 — citations need a handle to cite

Citations do two things: they let a reader verify a claim, and they make the
model's grounding inspectable. If an answer cites OPS-002 for something OPS-002
doesn't say, you've caught a specific, localisable failure.

The essential detail: **the citation marker must be present in the context you
supply.** `build_context_block` emits `--- SOURCE 1 [OPS-002] ---` so `[OPS-002]`
is a token the model can copy.

Ask for citations without supplying markers and you get invented references —
"[source 3]", "[Document 2, section 4]" — pointing at nothing. A citation format
the model has to construct is a citation format it will hallucinate.

## Rule 4 — specificity over paraphrase

Models default to smoothing. "Raise the pool size via `QUILL_PG_POOL_SIZE`, safe
up to 30" becomes "increase the connection pool size as needed" — fluent,
professional, and useless to someone at 3am during an incident.

For a runbook, the exact string is the entire value.

## Rule 5 — no extrapolation

The subtlest failure. The model finds a nearly-relevant chunk and bridges the gap
with "this probably means…". That produces an answer that is 80% grounded and
20% invented, with no marker separating them — strictly worse than an honest
refusal, because it *looks* sourced.

## What the baseline prompt deliberately does not do

```
You are a helpful assistant answering questions about internal
engineering systems. Answer from your own knowledge. Be concise
and specific.
```

No "say if you don't know." That's intentional: the baseline is meant to show
what a model does *by default* when asked about something it can't know. Adding a
refusal instruction to the control would be measuring prompt engineering, not
retrieval. The result — [[The Atlas Hallucination]] — is what default behaviour
looks like.

## An asymmetry worth noticing: thinking helps the baseline more

qwen3 is a hybrid reasoning model. Comparing runs with and without its `<think>`
phase:

- **Baseline** answers improve noticeably with thinking. Given room to reason,
  the model more often works its way toward acknowledging uncertainty.
- **Grounded** answers barely move.

That makes sense once stated: when the fact is sitting in the prompt, there isn't
much to reason *about*. The task is reading, not inference.

The practical implication is a cost lever. **Retrieval substitutes for reasoning
effort.** If your accuracy problem is "the model doesn't know," better context
will fix it more cheaply than more thinking tokens. If your problem is "the model
knows but reasons badly," retrieval won't help and effort will.

Knowing which problem you have is worth more than either tool.

## Things to try

- Delete rule 3, rebuild nothing, re-run `scripts.evaluate`. Watch the collision
  questions regress.
- Delete rule 1 and re-run. Watch `absent` questions go from refusal to invention.
- Remove the `[DOC-ID]` markers from `build_context_block` while keeping rule 2.
  Watch the model invent citation formats.

---
Next: [[08 - Measuring Whether Any Of This Worked]]
