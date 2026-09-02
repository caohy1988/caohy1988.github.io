---
type: Attested Computation
title: Active-customer revenue by region and quarter
description: The sanctioned computation for active-customer revenue, parameterized by billing country and quarter bounds.
status: stable
tags: [computation, revenue, bigquery]
runtime: bigquery
parameters:
  - { name: region, type: STRING, required: true }
  - { name: quarter_start, type: DATE, required: true }
  - { name: quarter_end, type: DATE, required: true }
computation: /references/computations/active_customer_revenue_by_region_quarter.sql
executor:
  resource: /references/executors/bigquery-named-parameters.md
  receipt:
    - bq_job_id
    - executed_artifact_hash
    - parameter_values
    - destination_table
    - job_started_at
    - job_ended_at
    - total_bytes_processed
attester:
  resource: /references/attesters/bq-job-metadata-attester.md
verified:
  - { by: "human:finance-data-governance@cymbal.example", at: 2026-05-12T09:30:00Z }
---

# Active-customer revenue by region and quarter

Computes [active-customer revenue](../metrics/active-customer-revenue.md) for
one billing country and one quarter. It applies the
[active customer](../concepts/active-customer.md) definition at `quarter_end`
and the [eligibility policy](../policies/revenue-recognition-eligibility.md)
to every line.

## Parameters

- `region` — ISO 3166-1 alpha-2 billing country, e.g. `DE`.
- `quarter_start`, `quarter_end` — first and last calendar day of the quarter.

Callers supply parameter values only. The SQL template is fixed; editing it,
adding parameters, or substituting another query voids attestation.

## Reads

- [billing_invoice_lines](../tables/billing-invoice-lines.md)
- [crm_customers](../tables/crm-customers.md)
