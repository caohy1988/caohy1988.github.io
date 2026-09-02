-- Sanctioned computation: active-customer revenue by region and quarter.
-- Contract: okf-phase0-mvp fixture bundle,
--   computations/active-customer-revenue-by-region-quarter.md
-- Named parameters only: @region STRING, @quarter_start DATE, @quarter_end DATE.
-- This template is the attested artifact; any edit voids attestation.

WITH active_customers AS (
  SELECT DISTINCT l.customer_id
  FROM `cymbal-finance-prod.finance_core.billing_invoice_lines` AS l
  WHERE l.line_status = 'PAID'
    AND l.line_type NOT IN ('REFUND', 'CREDIT_MEMO')
    AND l.invoice_date BETWEEN DATE_SUB(@quarter_end, INTERVAL 89 DAY)
                           AND @quarter_end
    -- BETWEEN is inclusive on both bounds: an 89-day back-off yields exactly
    -- 90 calendar dates ending at @quarter_end (the trailing-90-day window).
),
eligible_lines AS (
  SELECT
    l.customer_id,
    l.net_amount_usd
  FROM `cymbal-finance-prod.finance_core.billing_invoice_lines` AS l
  JOIN `cymbal-finance-prod.finance_core.crm_customers` AS c
    USING (customer_id)
  WHERE l.invoice_date BETWEEN @quarter_start AND @quarter_end
    AND l.line_status = 'PAID'
    AND l.line_type NOT IN ('REFUND', 'CREDIT_MEMO')
    AND c.billing_country = @region
    AND c.is_test_account = FALSE
    AND c.is_intercompany = FALSE
)
SELECT
  @region AS region,
  @quarter_start AS quarter_start,
  @quarter_end AS quarter_end,
  COUNT(DISTINCT e.customer_id) AS active_customers,
  ROUND(SUM(e.net_amount_usd), 2) AS active_customer_revenue_usd
FROM eligible_lines AS e
JOIN active_customers AS a
  USING (customer_id)
