---
title: Meridian On-Call Runbook
doc_id: OPS-002
owner: Platform Engineering
last_reviewed: 2026-08-02
---

# Meridian On-Call Runbook

On-call rotation is one week, Thursday 10:00 UTC to Thursday 10:00 UTC. The
handover meeting is Thursday at 09:30 UTC and is mandatory for both the outgoing
and incoming engineer.

## Severity definitions

| Severity | Definition                                                      | Response time | Who is woken |
|----------|-----------------------------------------------------------------|---------------|--------------|
| **SEV1** | Shipment creation failing, or data loss in progress              | 5 minutes     | Primary + secondary + Engineering Manager |
| **SEV2** | Degraded service, customer-visible, no data loss                 | 15 minutes    | Primary |
| **SEV3** | Internal-only degradation, no customer impact                    | Next business day | Nobody |

A SEV1 declaration is never wrong. If you are debating whether something is SEV1
or SEV2, it is SEV1. We have never had a post-incident review conclude that an
incident was over-escalated.

## Escalation path

1. **Primary on-call** — see PagerDuty schedule `meridian-primary`.
2. **Secondary on-call** — paged automatically if primary does not acknowledge
   within 8 minutes.
3. **Engineering Manager** — Priya Raghunathan. Paged on SEV1 or on secondary
   non-acknowledgement.
4. **Director of Platform** — Tomas Lindqvist. Paged only for SEV1 exceeding
   60 minutes, or any incident with suspected data loss.

Do not escalate to the Vantage Compliance vendor directly. All vendor escalation
goes through the Compliance team's shared inbox, because vendor contacts are
contractually routed through our account manager.

## Common alerts

### `HermesShipmentWriteLatencyHigh`

Fires when p99 write latency to CockroachDB exceeds 400ms for 5 minutes.

Most common cause is a hot range on the `shipments` table caused by ULID
prefixing — shipments created in the same millisecond land on the same range.
Check the CockroachDB hot ranges dashboard first.

**Mitigation:** Run `meridian-cli hermes rebalance --table shipments`. This
triggers a manual range split. It is safe to run in production and takes about
90 seconds. It does not require a maintenance window.

### `AtlasQueueDepthGrowing`

Fires when Atlas's in-memory event queue exceeds 50,000 items.

This is the alert that preceded the March 2026 outage. Atlas has no backpressure;
once the queue is growing faster than it drains, it will not recover on its own.

**Mitigation:** Scale Atlas replicas up *first*, then consider whether to pause
the consumer group. Command:
`kubectl -n meridian scale deploy/atlas --replicas=12`

The default replica count is 4. Do not exceed 16 — Atlas holds a PostGIS
connection per replica and the PostGIS instance caps at 200 connections shared
across all consumers.

### `SentryVantageTimeout`

Fires when the Vantage Compliance API returns 5xx or times out on more than 10%
of requests over 10 minutes.

Sentry has a circuit breaker that opens after 25 consecutive failures. When open,
shipments queue in `compliance_pending` rather than failing outright. This is the
intended behaviour — **do not** disable the circuit breaker to "let traffic
through", because unscreened shipments crossing a border is a regulatory
violation, not a degraded experience.

**Mitigation:** Confirm the circuit breaker is open, notify the Compliance team's
shared inbox, and wait. Shipments drain automatically when Vantage recovers.
There is a documented 4-hour regulatory window before queued shipments must be
manually reviewed.

### `QuillPoolExhausted`

Fires when Quill's Postgres connection pool has zero free connections for
2 minutes.

Nearly always month-end manifest generation. **Mitigation:** Raise the pool size
via the `QUILL_PG_POOL_SIZE` environment variable — it is safe up to 30. Restart
is required for the change to take effect. Longer-term fix is tracked as
MER-2988.

## What not to do

- Never run `meridian-cli hermes replay` in production without a written incident
  commander approval. It re-emits historical events and will duplicate billing
  records in Ledger, which takes roughly a day to unpick.
- Never restart Sentry mid-screening. In-flight screenings are not idempotent
  against the Vantage API and we are billed per call.
- Never scale Beacon below 3 replicas. Below 3, the Redis cache warm-up on
  deploy causes a visible latency spike for customers.
