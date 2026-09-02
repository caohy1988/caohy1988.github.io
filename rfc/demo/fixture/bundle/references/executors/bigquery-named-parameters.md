---
type: Executor Contract
title: BigQuery named-parameter executor
description: How sanctioned SQL in this bundle is executed and what a run must return.
status: stable
tags: [executor, bigquery]
---

# BigQuery named-parameter executor

Runs a sanctioned SQL template as a BigQuery query job under the **caller's
identity** (caller-delegated execution; BigQuery IAM is the authorization
source of truth).

Contract:

1. The job's `query` string is byte-identical to the referenced template file.
   No rendering, no concatenation, no comment stripping.
2. All parameters are BigQuery **named query parameters** matching the
   declared `parameters` list — same names, same types, no extras, none
   missing.
3. The result is written to a destination table in the caller's project; the
   executor never inlines results into prose as the evidence of record.

## Receipt fields a run must return

`bq_job_id`, `executed_artifact_hash` (SHA-256 of the template bytes),
`parameter_values`, `destination_table`, `job_started_at`, `job_ended_at`,
`total_bytes_processed`.
