---
type: Attested Computation
title: Active-customer revenue by region and quarter
description: Derived from BQAA observation, not authored. Observed at rank 2 of 6 in retrieval envelope okf:env-0f6c2b8a4d9e4f0a.
status: draft
tags: [bqaa-derived, observer-only, attested-computation]
runtime: bigquery
parameters:
  - { name: quarter_end, type: DATE, required: true }
  - { name: quarter_start, type: DATE, required: true }
  - { name: region, type: STRING, required: true }
executor:
  receipt:
    - bq_job_id
    - executed_artifact_hash
    - parameter_values
    - destination_table
    - job_started_at
    - job_ended_at
    - total_bytes_processed
sources:
  - resource: bqaa://cymbal-agents-prod.agent_analytics.agent_events?session_id=sess-4c1f9a2e7b3d
    title: BQAA observer trace 6f0c2a9e4b7d13a58c2e9f10d4b6a7c1 (google-adk-bq-logger/demo-fixture)
  - resource: okf:computation-version:sha256:c1ae34f977778f87b2bc7842b03130ced86619bea65b4657837b7204cac11c6b
    title: Sanctioned artifact in authored publication sha256:e92827f8b351a4db… (observed via receipt rcpt-7d1e5b903a2c48f1)
---
# Active-customer revenue by region and quarter

**Derived from BQAA observation, not authored.** This stub was emitted by
`okf-bqaa-adapter:v0` from `15` observer events in
`cymbal-agents-prod.agent_analytics.agent_events` (session `sess-4c1f9a2e7b3d`). The observer
sees titles, types, ranks, edges and receipts — never authored text,
bundle paths, `concept_version_id`, SQL, parameter values or the principal.

## Observed retrieval

- context_ref `okf:env-0f6c2b8a4d9e4f0a`, rank 2 of 6, mode `current`.
- Observed type `Attested Computation`; authored body not observed.

## Observed execution contract

- Runtime `bigquery`; 3 declared parameters (names and types only; values are never observed).
- No `computation:` artifact is declared here: the observer never sees SQL. The sanctioned artifact lives in the authored publication and is referenced by its `computation_version_id` under `sources`.
- Last observed verdict `UNVERIFIABLE` (`phase0_no_execution_or_integrity_proof`), receipt `rcpt-7d1e5b903a2c48f1`.
- Observed fail-closed errors before success: `parameter_binding_incomplete`.

Authored counterpart: `sha256:e92827f8b351a4db…` (publication_id observed on the tool span). This derived bundle (`bqaa-derived-cymbal-demo`) never writes back to it.
