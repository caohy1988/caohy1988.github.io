---
type: Metric
title: Customer revenue (legacy)
description: Derived from BQAA observation, not authored. Observed as excluded from current-mode retrieval (superseded; out of force since 2026-06-20).
status: deprecated
tags: [bqaa-derived, observer-only, metric]
sources:
  - resource: bqaa://cymbal-agents-prod.agent_analytics.agent_events?session_id=sess-4c1f9a2e7b3d
    title: BQAA observer trace 6f0c2a9e4b7d13a58c2e9f10d4b6a7c1 (google-adk-bq-logger/demo-fixture)
---
# Customer revenue (legacy)

**Derived from BQAA observation, not authored.** This stub was emitted by
`okf-bqaa-adapter:v0` from `15` observer events in
`cymbal-agents-prod.agent_analytics.agent_events` (session `sess-4c1f9a2e7b3d`). The observer
sees titles, types, ranks, edges and receipts — never authored text,
bundle paths, `concept_version_id`, SQL, parameter values or the principal.

## Observed exclusion

Excluded from `current`-mode retrieval: superseded; out of force since 2026-06-20.
The current definition is [Active-customer revenue](active-customer-revenue.md).

Authored counterpart: `sha256:e92827f8b351a4db…` (publication_id observed on the tool span). This derived bundle (`bqaa-derived-cymbal-demo`) never writes back to it.
