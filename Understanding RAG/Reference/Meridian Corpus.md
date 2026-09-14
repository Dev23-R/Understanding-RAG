---
tags: [reference, corpus]
---

# Meridian Corpus

The eight documents in `corpus/`. **Every fact in them is invented.** Meridian,
Northwind Freight, and every person named are fictional.

## Why fictional

This is the design decision that makes the whole experiment clean, and it's worth
understanding before reading the results.

If the corpus were real documentation — the Kubernetes docs, a public codebase —
you could never separate two explanations for a correct answer:

1. Retrieval worked.
2. The model already knew it from pretraining.

With an invented corpus there's no ambiguity. The model provably cannot know any
of it, so **any correct answer must have come from retrieval**. That's what makes
the baseline's 2/14 interpretable rather than just low.

The cost is that 14% is a *floor*, not a realistic baseline for a corpus where
the model knows something. On real documentation the baseline would score higher
and the RAG delta would be smaller. That caveat is recorded in [[Eval Results]].

## The documents

| Doc ID | File | Content |
|---|---|---|
| `ARCH-001` | `architecture-overview.md` | Six services, request flow, environments, known debt |
| `OPS-002` | `oncall-runbook.md` | Severities, escalation, four alerts with mitigations |
| `API-003` | `api-conventions.md` | Versioning, ULID prefixes, pagination, errors, rate limits, webhooks |
| `ADR-014` | `adr-014-event-bus.md` | Why Redpanda, alternatives rejected, consequences |
| `OPS-004` | `deployment-pipeline.md` | Stages, soak period, deploy windows, rollback, feature flags |
| `DATA-005` | `data-retention-policy.md` | Residency, retention periods, pseudonymisation, erasure |
| `PM-2026-03-11` | `postmortem-2026-03-atlas.md` | The Atlas cascade failure, timeline, root causes, action items |
| `REF-006` | `glossary.md` | Terms, including the deliberate name collisions |

## The services

| Service | Language | Does |
|---|---|---|
| Hermes | Go | Shipment routing; the only writer to `shipments` |
| Atlas | Go | Geospatial hub capacity modelling |
| Ledger | Java | Billing and settlement |
| Sentry | Rust | Customs compliance and sanctions screening |
| Quill | Python | Document generation |
| Beacon | TypeScript | Customer-facing API and webhooks |

## Design features, and what each one tests

**Name collisions.** Every service name collides with a well-known product —
Atlas/MongoDB Atlas, Sentry/Sentry.io, Beacon, Hermes, Quill. This is realistic
(organisations name things this way constantly) and it creates strong,
*specifically wrong* priors for grounding to overcome. It's what produced
[[The Atlas Hallucination]], and it's what the `collision` eval category tests.

**Cross-document dependencies.** Facts are deliberately split so some questions
cannot be answered from one document:

- Bus retention is 30 days (`ADR-014`); *why* it must be under 90 is in
  `DATA-005`.
- Two regional stacks (`ARCH-001`); the GDPR reason is in `DATA-005`.
- The `HermesShipmentWriteLatencyHigh` alert (`OPS-002`); the ULID hot-range
  cause is explained in `API-003`.

This is what the `multihop` category tests, and what sets a floor on `TOP_K`
([[06 - Context Is Not Free]]).

**Specific, checkable values.** `QUILL_PG_POOL_SIZE`, 45-minute soak, 16 replicas,
`stl_` prefix, 200 PostGIS connections. Exact strings make deterministic grading
possible ([[08 - Measuring Whether Any Of This Worked]]).

**Documented absences.** The corpus states Vantage has *no SLA*. That's different
from information simply not being present, and q14 tests that the system doesn't
collapse the two into a blanket refusal.

**Genuine gaps.** Nothing about HR policy, team headcount, or salaries — but the
corpus *does* contain real names in other roles, so a weak system has everything
it needs to invent a plausible team roster. That's what q13 is for.

**Deliberate tension.** `DATA-005` says shipment records are deleted at 90 days
*and* that screening results are kept 7 years. That looks contradictory and is
resolved by pseudonymisation. Good test of whether the model reads carefully or
pattern-matches to the first number it finds.

## Using your own documents instead

Drop markdown into `corpus/` and rebuild. Frontmatter `title` and `doc_id` are
used if present; otherwise the first H1 and the filename are used.

Your Obsidian vault is an obvious candidate and would be a genuinely useful
second corpus — but note that it changes the experiment. Your notes are *your*
writing about topics the model likely knows something about, so the clean
separation described above disappears. That's fine for building something useful;
just don't read the resulting numbers as a measurement of retrieval the way
[[Eval Results]] can be.
