---
type: Policy
title: Revenue recognition eligibility
description: Which invoice lines count toward recognized revenue metrics, and how regions are attributed.
status: stable
tags: [policy, revenue, finance]
sources:
  - resource: https://intranet.cymbal.example/finance/policies/rev-rec-eligibility-2026.html
    title: Revenue recognition eligibility (2026)
    author: "human:finance-controller@cymbal.example"
verified:
  - { by: "human:finance-controller@cymbal.example", at: 2026-04-02T15:00:00Z }
stale_after: 2027-04-02T00:00:00Z
---

# Revenue recognition eligibility

An invoice line in [billing_invoice_lines](../tables/billing-invoice-lines.md)
is **eligible** for recognized-revenue metrics when all of the following hold:

1. `line_status = 'PAID'`.
2. `line_type NOT IN ('REFUND', 'CREDIT_MEMO')` — refunds and credits are
   netted out by exclusion, not subtracted twice.
3. The customer is not a test account (`is_test_account = FALSE` in
   [crm_customers](../tables/crm-customers.md)).
4. The customer is not an intercompany entity (`is_intercompany = FALSE`).

## Regional attribution

Revenue is attributed to the customer's **billing country**
(`crm_customers.billing_country`, ISO 3166-1 alpha-2). Shipping country is
never used for revenue attribution.

## Amount basis

Use `net_amount_usd` (post-discount, pre-tax). Gross amounts are not
recognized revenue.
