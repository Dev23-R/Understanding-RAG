---
title: "ADR-014: Event bus selection"
doc_id: ADR-014
status: Accepted
date: 2025-11-20
deciders: Priya Raghunathan, Tomas Lindqvist, Wen Chen
---

# ADR-014: Event bus selection

## Status

Accepted, 2025-11-20. Supersedes ADR-009 (RabbitMQ).

## Context

Until late 2025 Meridian used RabbitMQ for inter-service messaging. Three
problems forced a reconsideration:

1. **No replay.** When Ledger had a billing bug in August 2025, we could not
   reprocess the affected period. We reconstructed 11 days of settlements by
   hand from CockroachDB audit rows.
2. **Consumer coupling.** Adding Sentry to the pipeline required changing
   Hermes's publishing code, because RabbitMQ exchanges were configured per
   consumer.
3. **Ordering.** We needed per-shipment ordering guarantees. RabbitMQ gives
   ordering per queue, not per key, so a shipment's events could interleave
   across consumers.

## Decision

We adopted **Redpanda** (Kafka-protocol compatible) as the platform event bus.

Topics are partitioned by `shipment_id`, which gives us per-shipment ordering
without global ordering cost. Retention is 30 days on all topics, which is what
makes replay possible.

### Why Redpanda over Kafka

The deciding factor was operational cost, not performance. Redpanda has no
ZooKeeper/KRaft quorum to operate separately and runs as a single binary. With a
platform team of nine people, the Kafka operational burden was judged higher than
the benefit of a larger ecosystem.

We explicitly did **not** choose Redpanda for its latency claims. Our p95 budget
is 30 seconds end-to-end; broker latency was never the constraint.

### Why not NATS JetStream

NATS was seriously considered and rejected on one point: at evaluation time its
compacted-stream semantics did not give us the replay-from-offset behaviour we
needed for billing reconstruction. This may have changed since; the decision
should be revisited if we ever reopen it.

## Topic naming convention

`<domain>.<entity>.<past-tense-verb>`

Examples: `shipment.created`, `routing.assigned`, `compliance.blocked`,
`shipment.state_changed`, `settlement.opened`.

Events are named in the past tense because an event is a record of something that
already happened. A message named `shipment.create` would be a command, and
commands belong on gRPC, not the bus.

## Consequences

**Positive:**
- Replay from any offset within 30 days. Used successfully twice since adoption.
- New consumers attach without touching producers.
- Per-shipment ordering is guaranteed by partition key.

**Negative:**
- **At-least-once delivery, not exactly-once.** Every consumer must be
  idempotent. This is the single biggest source of bugs introduced by this
  decision. Ledger in particular had to add a `processed_events` dedupe table.
- 30-day retention on all topics costs roughly €2,100/month in storage across
  both regions.
- Redpanda expertise on the team is concentrated in two engineers. This is a
  known bus-factor risk, tracked as an item in the Q3 2026 team plan.

## Compliance note

Because retention is 30 days and events contain shipper names and addresses,
event bus data falls under the same GDPR retention rules as the primary
datastores. See DATA-005. The 30-day window was chosen specifically to sit
inside the 90-day limit defined there.
