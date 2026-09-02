---
type: Metric
title: Active-customer revenue
description: Recognized net revenue in a period from customers active at period end, attributed by billing country.
status: stable
tags: [revenue, metric, finance]
supersedes:
  - metrics/customer-revenue-legacy.md
links:
  - target: policies/revenue-recognition-eligibility.md
    rel: governed_by
    confidence: extracted
sources:
  - resource: https://intranet.cymbal.example/finance/metrics/acr-definition-v3.html
    title: ACR definition v3 (finance council, 2026-02)
verified:
  - { by: "human:finance-data-governance@cymbal.example", at: 2026-05-12T09:30:00Z }
stale_after: 2027-02-01T00:00:00Z
---

# Active-customer revenue

The sum of **net** invoice-line amounts (USD) recognized in the period, over
customers who are [active](../concepts/active-customer.md) at period end,
restricted to eligible lines under the
[revenue recognition eligibility policy](../policies/revenue-recognition-eligibility.md).

Regional attribution uses the customer's **billing country** from
[crm_customers](../tables/crm-customers.md) — never the shipping country.
That is the change from the superseded
[legacy customer revenue](customer-revenue-legacy.md) definition, affirmed by
the finance council on 2026-06-20 (see the bundle log).

## Sanctioned computation

The only sanctioned way to produce this number is
[active-customer revenue by region and quarter](../computations/active-customer-revenue-by-region-quarter.md).
Hand-written SQL that resembles this metric is not this metric.

## Inputs

- [billing_invoice_lines](../tables/billing-invoice-lines.md) — amounts, line status, line type, dates.
- [crm_customers](../tables/crm-customers.md) — billing country, test-account and intercompany flags.
