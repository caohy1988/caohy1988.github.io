---
type: Business Concept
title: Active customer
description: A customer with at least one paid, non-refunded invoice line in the trailing 90 days.
status: stable
tags: [customers, finance, revenue]
sources:
  - resource: https://intranet.cymbal.example/finance/policies/customer-activity-2024.html
    title: Customer activity policy (2024 revision)
    author: "human:finance-data-governance@cymbal.example"
verified:
  - { by: "human:finance-data-governance@cymbal.example", at: 2026-05-12T09:30:00Z }
stale_after: 2027-05-12T00:00:00Z
---

# Active customer

A customer is **active** at a reference date when it has at least one invoice
line in [billing_invoice_lines](../tables/billing-invoice-lines.md) that is:

- `line_status = 'PAID'`,
- not a refund or credit memo (`line_type NOT IN ('REFUND', 'CREDIT_MEMO')`),
- dated within the 90 days ending at the reference date.

For a quarterly question, the reference date is the last day of the quarter.

## What this is not

- Not "has a login" or "has an open contract". Activity is billing activity.
- Not gross activity: refunded and credited lines never count, per the
  [revenue recognition eligibility policy](../policies/revenue-recognition-eligibility.md).

## Used by

- [Active-customer revenue](../metrics/active-customer-revenue.md), the only
  metric sanctioned to aggregate revenue over this population.
