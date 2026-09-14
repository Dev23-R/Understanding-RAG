---
title: Meridian Deployment Pipeline
doc_id: OPS-004
owner: Platform Engineering
last_reviewed: 2026-07-28
---

# Meridian Deployment Pipeline

## Overview

All six services deploy through the same pipeline. There are no exceptions, no
manual deploys, and no way to push to production from a laptop. The pipeline is
defined in `meridian-infra/pipelines/` and changes to it require review from two
platform engineers.

## Stages

```
commit → CI → staging → soak → prod-eu → prod-us
```

1. **CI** — unit tests, lint, container build. Target under 8 minutes. Currently
   averages 6m 40s; Ledger is the slowest at 11 minutes and is the reason the
   overall target is missed roughly once a week.
2. **staging** — automatic on merge to `main`. Runs the integration suite against
   an anonymised data copy.
3. **soak** — the deploy sits in staging for **45 minutes** under synthetic load
   before promotion unlocks. This exists because our worst historical bugs were
   memory leaks and connection-pool exhaustion, neither of which shows up in a
   30-second smoke test.
4. **prod-eu** — requires a human click. Canary at 5% for 10 minutes, then 50%
   for 10 minutes, then 100%.
5. **prod-us** — unlocks only 2 hours after `prod-eu` reaches 100%. The gap is
   deliberate: it means a bad deploy hits one region, not both.

## Deploy windows

Deploys to production are permitted Monday to Thursday, 08:00–16:00 in the target
region's local business hours.

**No Friday deploys.** This is not a suggestion. The rule exists because three of
our five longest incidents began with a Friday afternoon deploy and were
prolonged by reduced weekend staffing.

Exceptions require incident commander approval and are logged. Security patches
are the usual exception and are pre-approved for any window.

## Rollback

Rollback is a first-class pipeline action, not a re-deploy of the previous
commit: `meridian-cli deploy rollback --service <name> --env <env>`

Target rollback time is under 4 minutes. Measured median across 2026 is
2m 51s.

**Database migrations are the exception.** A deploy containing a migration cannot
be rolled back automatically. We therefore require all migrations to be
**expand-contract**: the schema change ships in one deploy (expand, backwards
compatible), the code change in a later deploy, and the cleanup (contract) in a
third. A migration that cannot be expressed this way requires a written plan
approved by the Engineering Manager before merge.

## Feature flags

Flags are held in LaunchDarkly. Convention:

- Flag keys are `snake_case`, prefixed with the owning service: `hermes_new_router`.
- Every flag has an owner and an expiry date at creation. Flags past expiry appear
  on the weekly platform review.
- Flags are **not** a substitute for expand-contract migrations. A flag controls
  code paths, not schema.

As of the July 2026 review there are 34 active flags, 11 of them past their expiry
date. The oldest is `ledger_dual_write_settlement`, created 2025-04-02, which is
past expiry by over a year and is load-bearing — removing it requires the Ledger
settlement rewrite tracked as MER-2401.

## What breaks the pipeline most often

In descending order, from 2026 data:

1. Flaky integration tests in the staging stage (roughly 40% of pipeline failures).
   The worst offender is the Sentry compliance suite, which depends on a Vantage
   sandbox with no uptime guarantee.
2. Container registry rate limits during high-activity periods.
3. Soak-stage memory alarms on Quill during month-end, which are real signal
   rather than flakes and correctly block promotion.
