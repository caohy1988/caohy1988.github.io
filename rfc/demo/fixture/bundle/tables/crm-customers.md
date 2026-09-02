---
type: BigQuery Table
title: CRM customers
description: One row per customer with billing attributes and account flags.
status: stable
resource: https://console.cloud.google.com/bigquery?p=cymbal-finance-prod&d=finance_core&t=crm_customers
tags: [crm, customers, table]
sources:
  - resource: https://intranet.cymbal.example/dataeng/pipelines/crm-sync.html
    title: CRM sync pipeline
verified:
  - { by: "human:data-platform@cymbal.example", at: 2026-05-02T11:00:00Z }
---

# Schema

| Column            | Type    | Description                                                |
|-------------------|---------|------------------------------------------------------------|
| `customer_id`     | STRING  | Globally unique customer identifier.                       |
| `billing_country` | STRING  | ISO 3166-1 alpha-2 billing country, e.g. `DE`.             |
| `shipping_country`| STRING  | ISO 3166-1 alpha-2 shipping country. Not used for revenue. |
| `is_test_account` | BOOL    | Internal or synthetic account.                             |
| `is_intercompany` | BOOL    | Cymbal-owned entity billing another Cymbal entity.         |

# Joins

Joined with [billing_invoice_lines](billing-invoice-lines.md) on `customer_id`.
