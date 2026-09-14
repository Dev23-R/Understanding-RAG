---
title: Meridian Data Retention and Residency Policy
doc_id: DATA-005
owner: Compliance
last_reviewed: 2026-05-19
---

# Meridian Data Retention and Residency Policy

This policy governs how long Meridian retains data and where that data may
physically reside. It is binding on all six platform services.

## Residency

| Data class                  | `prod-eu` may store | `prod-us` may store |
|-----------------------------|---------------------|---------------------|
| Shipper personal data       | EU only             | US only             |
| Consignee personal data     | EU only             | US only             |
| Shipment metadata (no PII)  | Either              | Either              |
| Carrier commercial terms    | Either              | Either              |
| Customs screening results   | EU only             | US only             |

Personal data must not cross the regional boundary. This is why the platform
runs two fully independent stacks rather than one multi-region deployment (see
ARCH-001). A cross-region shipment is modelled as two linked shipments precisely
so that each region holds only its own side's personal data.

The `sibling_shipment_id` link is permitted to cross regions because it is an
opaque identifier carrying no personal data.

## Retention periods

| Data                              | Retention | Basis                       |
|-----------------------------------|-----------|-----------------------------|
| Shipment records (incl. PII)      | 90 days after delivery | GDPR minimisation  |
| Customs screening results         | 7 years   | Customs regulation          |
| Settlement and invoice records    | 7 years   | Tax law                     |
| Event bus topics                  | 30 days   | Operational (see ADR-014)   |
| Application logs                  | 14 days   | Operational                 |
| Audit logs (who accessed what)    | 2 years   | Security policy             |
| Generated documents (bills of lading) | 7 years | Customs regulation        |

Note the apparent conflict: shipment records are deleted at 90 days, but customs
screening results and generated documents are retained 7 years. This is
intentional and legally required. The 7-year records are **pseudonymised** at the
90-day mark — personal identifiers are replaced with the shipment ULID, and the
mapping table is destroyed. After 90 days it is not possible to re-identify a
shipper from a retained screening record.

This pseudonymisation job runs nightly at 02:00 in each region's local time and
is owned by Sentry. If it fails, it pages SEV2 — not SEV3 — because a missed run
puts us outside the GDPR commitment within 24 hours.

## The 30-day event bus window

Event bus retention is 30 days, chosen to sit comfortably inside the 90-day
shipment window. This matters because event payloads contain shipper names and
addresses in plaintext. If bus retention exceeded 90 days we would be retaining
personal data past the deletion commitment through a side channel.

Any proposal to extend bus retention beyond 30 days requires Compliance sign-off,
not just Platform Engineering approval.

## Deletion requests

A GDPR erasure request is served within 30 days. The process is:

1. Compliance receives the request and verifies identity.
2. Compliance files a ticket to the `meridian-erasure` queue.
3. Sentry's erasure job removes personal data from PostgreSQL and triggers
   tombstone events on the bus so compacted topics drop the payloads.
4. Quill re-generates affected documents in pseudonymised form.
5. Compliance confirms completion to the requester.

Step 3 is the one that most often fails, because tombstones only take effect on
compacted topics and three of our topics are time-retained rather than compacted.
For those, the data ages out at 30 days instead of being actively erased. This
gap is documented and accepted — 30 days is inside the 30-day erasure SLA, but
only just, and Compliance has flagged it as a risk if bus retention ever grows.

## Backups

Database backups are retained 35 days. Backups are **not** exempt from erasure
requests, but erasure from backups is deferred: we do not restore-and-scrub.
Instead, the erasure ticket remains open until the last backup containing the
data ages out, at which point it is closed automatically. This is disclosed in
the customer Data Processing Agreement.
