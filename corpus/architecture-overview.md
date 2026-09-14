---
title: Meridian Platform Architecture Overview
doc_id: ARCH-001
owner: Platform Engineering
last_reviewed: 2026-07-14
---

# Meridian Platform Architecture Overview

Meridian is Northwind Freight's internal logistics platform. It coordinates
shipment routing, carrier bidding, and customs documentation across 14 regional
hubs.

## Service topology

The platform is decomposed into six primary services. All inter-service
communication goes through the event bus (see ADR-014) except where noted.

| Service    | Language | Responsibility                                      | Datastore        |
|------------|----------|-----------------------------------------------------|------------------|
| **Hermes** | Go       | Shipment routing and carrier assignment              | CockroachDB      |
| **Atlas**  | Go       | Geospatial hub capacity modelling                    | PostGIS          |
| **Ledger** | Java     | Billing, invoicing, carrier settlement               | PostgreSQL       |
| **Sentry** | Rust     | Customs document validation and compliance screening | PostgreSQL       |
| **Quill**  | Python   | Document generation (bills of lading, manifests)     | S3 + PostgreSQL  |
| **Beacon** | TypeScript | Customer-facing status API and webhooks            | Redis + Postgres |

Hermes is the only service permitted to write to the `shipments` table. Every
other service reads shipment state from the `shipment.state_changed` event
stream. This constraint exists because we had three separate write paths until
2025 and reconciling them consumed roughly 40% of on-call time.

## Request flow: creating a shipment

1. Client calls `POST /v2/shipments` on **Beacon**.
2. Beacon validates the payload shape and forwards to **Hermes** over gRPC.
   This is the one synchronous inter-service hop in the platform.
3. Hermes writes the shipment row, assigns a `shipment_id` (ULID format,
   prefixed `shp_`), and emits `shipment.created` to the bus.
4. **Atlas** consumes `shipment.created`, computes hub routing, and emits
   `routing.assigned` within a 2-second target.
5. **Sentry** consumes `routing.assigned` and screens against sanctions lists.
   If screening fails, it emits `compliance.blocked` and the shipment halts.
6. **Quill** consumes `compliance.cleared` and generates documents.
7. **Ledger** consumes `shipment.delivered` and opens a settlement record.

The end-to-end target for steps 1-6 is 30 seconds at p95. As of the July 2026
review we sit at 22 seconds p95, 71 seconds p99. The p99 is dominated by Sentry
sanctions screening, which calls an external provider (Vantage Compliance API)
with no SLA.

## Environments

| Environment | Cluster            | Purpose                            | Data          |
|-------------|--------------------|------------------------------------|---------------|
| `dev`       | `mer-dev-euw1`     | Developer sandboxes, reset nightly | Synthetic     |
| `staging`   | `mer-stg-euw1`     | Pre-production verification        | Anonymised copy |
| `prod-eu`   | `mer-prod-euw1`    | European traffic                   | Live          |
| `prod-us`   | `mer-prod-use1`    | North American traffic             | Live          |

There is deliberately **no** shared database between `prod-eu` and `prod-us`.
The two regions are fully independent stacks; a shipment crossing regions is
modelled as two linked shipments with a `sibling_shipment_id` reference. This
was a GDPR-driven decision, not a performance one.

## Known architectural debt

- **Beacon's Redis cache has no invalidation on `shipment.cancelled`.** Cancelled
  shipments can show as active for up to 90 seconds (the TTL). Tracked as
  MER-3341, unresolved as of this review.
- **Quill runs a single-writer Postgres connection pool** sized at 12, which
  becomes the bottleneck during month-end manifest generation.
- **Atlas has no backpressure mechanism.** It will happily accept events faster
  than it can process them and grow its in-memory queue until the pod OOMs.
  This caused the March 2026 incident (see PM-2026-03-11).
