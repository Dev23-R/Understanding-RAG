---
title: "Postmortem: Atlas cascade failure, 11 March 2026"
doc_id: PM-2026-03-11
severity: SEV1
duration: 3h 47m
author: Wen Chen
status: Action items open
---

# Postmortem: Atlas cascade failure, 11 March 2026

## Summary

On 11 March 2026, a marketing campaign drove a 6x spike in shipment creation.
Atlas, which has no backpressure mechanism, accepted events faster than it could
process them, exhausted pod memory, and entered a crash loop. Because Atlas is
in the critical path between `shipment.created` and `compliance.cleared`, all
new shipments stalled before document generation.

Customer impact: 41,300 shipments delayed. No data loss. Duration 3 hours
47 minutes from first alert to full drain.

**This was not a capacity problem.** Atlas had sufficient CPU headroom
throughout. The failure was a design gap: an unbounded in-memory queue.

## Timeline (UTC)

| Time  | Event |
|-------|-------|
| 08:14 | Marketing campaign email sends. Shipment creation rate rises from ~180/min to ~1,100/min. |
| 08:22 | `AtlasQueueDepthGrowing` fires. Queue at 50,000. |
| 08:24 | Primary on-call acknowledges. |
| 08:31 | Primary scales Atlas from 4 to 8 replicas. Queue continues growing. |
| 08:39 | First Atlas pod OOMKilled. Restart begins. |
| 08:41 | **Critical mistake.** On restart, Atlas re-reads from its last committed offset. Because commits are batched every 30 seconds, the restarted pod reprocesses up to 30s of events, adding load to an already-saturated system. |
| 08:47 | Cascade: all 8 pods now in crash loop. Queue depth unmeasurable (metrics endpoint down with the pods). |
| 08:52 | SEV1 declared. Secondary and EM paged. |
| 09:05 | Incident commander (Priya) decides to **pause the consumer group** rather than scale further. |
| 09:07 | Consumer group paused. Atlas pods stabilise with empty queues. |
| 09:15 | Atlas scaled to 16 replicas while paused. |
| 09:20 | Consumer group resumed with a manually-set `max.poll.records` of 50 (default was 500). |
| 09:24 | Queue begins draining. Drain rate ~2,400 events/min. |
| 12:01 | Queue empty. All shipments processed. |
| 12:01 | Incident closed. |

## Root causes

This incident had three contributing causes, not one.

1. **Atlas has no backpressure.** It calls `poll()` in a loop and pushes results
   onto an unbounded `chan`. There is no mechanism to slow consumption when the
   processing goroutines fall behind. This is the primary cause.

2. **Offset commits are batched at 30 seconds.** On a crash-loop restart this
   converts one failure into repeated reprocessing, which is what turned a
   single OOM into a cascade.

3. **The runbook advised scaling first.** At the time, `AtlasQueueDepthGrowing`
   documentation said to scale replicas. Under crash-loop conditions scaling adds
   consumers that also crash, accelerating the cascade. The runbook has since
   been amended to say scale first *only if pods are healthy*.

## What went well

- Pausing the consumer group was the correct call and was made within 13 minutes
  of SEV1 declaration.
- No data was lost. At-least-once delivery plus idempotent consumers meant the
  reprocessing in step 08:41 was harmless to correctness, only to load.
- Redpanda's 30-day retention meant there was never a risk of losing events while
  the consumer was paused.

## What went poorly

- 38 minutes elapsed between the first alert and SEV1 declaration. The alert
  fired at 08:22 and the failure mode was already understood by 08:39.
- We had no dashboard showing consumer group lag, only in-pod queue depth. When
  the pods died we went blind. Lag is a broker-side metric and would have stayed
  visible.

## Action items

| ID | Action | Owner | Status |
|----|--------|-------|--------|
| AI-1 | Add bounded channel + backpressure to Atlas consumer | Wen Chen | **Open** |
| AI-2 | Reduce Atlas offset commit interval to 5 seconds | Wen Chen | Done 2026-03-19 |
| AI-3 | Add broker-side consumer lag dashboard for all consumer groups | Ravi Menon | Done 2026-04-02 |
| AI-4 | Amend `AtlasQueueDepthGrowing` runbook entry | Priya Raghunathan | Done 2026-03-14 |
| AI-5 | Load test Atlas at 10x baseline before Q4 peak season | Wen Chen | **Open** |

AI-1 remains open as of the August 2026 runbook review. It is the highest-priority
item in the platform backlog and is the reason the March failure mode is still
technically reachable.
