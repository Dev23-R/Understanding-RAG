---
title: Meridian API Conventions
doc_id: API-003
owner: Beacon Team
last_reviewed: 2026-06-30
---

# Meridian API Conventions

These conventions apply to the public Beacon API (`api.meridian.northwind.example`)
and to internal gRPC service definitions.

## Versioning

The public API is versioned in the path: `/v1/`, `/v2/`. We are currently on
**v2**. v1 was sunset on 2026-01-31 and now returns `410 Gone` with a link to
the migration guide.

We version the whole API, not individual endpoints. A breaking change anywhere
increments the version everywhere. This is more disruptive per change and
deliberately so — it makes us batch breaking changes rather than dribble them
out, and clients only have to migrate once.

Internal gRPC services are **not** versioned in the package path. Instead they
follow a strict additive-only rule: fields may be added, never removed or
renumbered. If a field must go, it is marked `reserved` and left dead.

## Identifiers

All public identifiers are ULIDs with a type prefix and an underscore:

| Entity      | Prefix  | Example                           |
|-------------|---------|-----------------------------------|
| Shipment    | `shp_`  | `shp_01JQRX8K4M2Y7ZNV3TBW9HEDGC`  |
| Carrier     | `car_`  | `car_01JQRX8K4M2Y7ZNV3TBW9HEDGC`  |
| Hub         | `hub_`  | `hub_01JQRX8K4M2Y7ZNV3TBW9HEDGC`  |
| Settlement  | `stl_`  | `stl_01JQRX8K4M2Y7ZNV3TBW9HEDGC`  |
| Document    | `doc_`  | `doc_01JQRX8K4M2Y7ZNV3TBW9HEDGC`  |

ULIDs were chosen over UUIDv4 for lexicographic sortability by creation time.
Note the tradeoff documented in OPS-002: ULID prefixing causes hot ranges in
CockroachDB, which is the cause of the `HermesShipmentWriteLatencyHigh` alert.
We consider this an acceptable trade because the mitigation is cheap and
sortable IDs simplify pagination substantially.

Internal database primary keys are **not** ULIDs — they are `bigint` sequences.
The ULID is a separate indexed column. Exposing sequence IDs publicly would leak
volume information to competitors.

## Pagination

Cursor-based only. We do not support offset pagination on any endpoint.

```
GET /v2/shipments?limit=50&cursor=eyJpZCI6InNocF8wMUpR...
```

Responses carry a `next_cursor` field, `null` when exhausted. `limit` defaults to
25 and caps at 200. Requesting more than 200 returns `400`, it does not silently
clamp — silent clamping caused a customer to believe they had received all
results when they had not.

## Errors

All errors return a consistent envelope:

```json
{
  "error": {
    "type": "validation_error",
    "code": "shipment_destination_unsupported",
    "message": "Destination hub hub_01JQ... is not accepting shipments.",
    "request_id": "req_01JQRX8K4M2Y7ZNV3TBW9HEDGC"
  }
}
```

`type` is a coarse category from a closed set: `validation_error`,
`authentication_error`, `permission_error`, `not_found`, `rate_limit_error`,
`compliance_error`, `internal_error`.

`code` is specific and from an open set — new codes may appear at any time
without a version bump. Clients must not exhaustively match on `code`; they must
have a default branch. This is stated explicitly because two integration partners
have shipped code that crashed on an unknown `code`.

Always include `request_id` when contacting support. It is also returned in the
`X-Meridian-Request-Id` response header on every request, including successes.

## Rate limits

| Tier       | Requests/minute | Burst |
|------------|-----------------|-------|
| Sandbox    | 60              | 100   |
| Standard   | 600             | 1,000 |
| Enterprise | 6,000           | 10,000|

Limits are per API key, not per organisation. Rate limit state is held in Beacon's
Redis. On a Redis failure we **fail open** — requests are allowed through
unlimited. This is a deliberate availability-over-enforcement choice, documented
here so it is not mistaken for a bug.

Rate limit headers are returned on every response:
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (Unix seconds).

## Webhooks

Beacon delivers webhooks for `shipment.state_changed` and `compliance.blocked`
only. Not every internal event is exposed externally.

Delivery is at-least-once with exponential backoff: 6 attempts over roughly
17 hours (1m, 5m, 25m, 2h, 6h, 8h). After the sixth failure the webhook is
marked `dead` and must be replayed manually from the dashboard.

Every webhook payload is signed with HMAC-SHA256 in the `X-Meridian-Signature`
header. The signing secret rotates every 90 days; both the current and previous
secret are valid during a 24-hour overlap window.
