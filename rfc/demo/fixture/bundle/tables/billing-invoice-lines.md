---
type: BigQuery Table
title: Billing invoice lines
description: One row per invoice line across all billing systems, in USD.
status: stable
resource: https://console.cloud.google.com/bigquery?p=cymbal-finance-prod&d=finance_core&t=billing_invoice_lines
tags: [billing, revenue, table]
sources:
  - resource: https://intranet.cymbal.example/dataeng/pipelines/billing-ingest.html
    title: Billing ingest pipeline
verified:
  - { by: "human:data-platform@cymbal.example", at: 2026-05-02T11:00:00Z }
---

# Schema

| Column           | Type    | Description                                                  |
|------------------|---------|--------------------------------------------------------------|
| `invoice_line_id`| STRING  | Globally unique invoice line identifier.                     |
| `customer_id`    | STRING  | Foreign key into [crm_customers](crm-customers.md).          |
| `invoice_date`   | DATE    | Date the line was invoiced.                                  |
| `line_status`    | STRING  | `PAID`, `OPEN`, `VOID`.                                      |
| `line_type`      | STRING  | `CHARGE`, `REFUND`, `CREDIT_MEMO`.                           |
| `net_amount_usd` | NUMERIC | Post-discount, pre-tax amount in USD. Negative for refunds.  |

# Joins

Joined with [crm_customers](crm-customers.md) on `customer_id`.
