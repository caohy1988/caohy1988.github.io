# Fixture: "What was active-customer revenue in Germany last quarter — and can I trust the number?"

One OKF v0.2 bundle (`bundle/`, fictional Cymbal data, 11 files) that
**models the intended end-to-end flow** for the RFC's motivating question —
no query, executor, or attester was actually executed in Phase 0. Every
later phase gate regresses against it. It uses zero new required OKF keys: core §4.1 keys, §10.2
computation keys, and two tolerated producer extensions (`supersedes` per
PR #195, `links` per #183).

## The path, file by file

**Question → concept.** "Active-customer revenue" resolves to the metric
[`metrics/active-customer-revenue.md`](bundle/metrics/active-customer-revenue.md),
which leans on the population definition in
[`concepts/active-customer.md`](bundle/concepts/active-customer.md): paid,
non-refunded billing activity in the trailing 90 days. Retrieval in `current`
mode **excludes** [`metrics/customer-revenue-legacy.md`](bundle/metrics/customer-revenue-legacy.md) —
it is `deprecated` and out-of-force via the affirmed supersession (log entry
2026-06-20). That exclusion is half the "can I trust it" answer: the old
definition (gross amounts, shipping country) would overstate Germany.

**Concept → eligibility.** The metric is governed by
[`policies/revenue-recognition-eligibility.md`](bundle/policies/revenue-recognition-eligibility.md):
paid lines only, no refunds/credits, no test or intercompany accounts, net
USD amounts, **billing-country** attribution.

**Eligibility → sanctioned computation.** The only sanctioned way to produce
the number is
[`computations/active-customer-revenue-by-region-quarter.md`](bundle/computations/active-customer-revenue-by-region-quarter.md)
(OKF §10.2: `runtime: bigquery`, three declared parameters, fixed SQL
template, executor and attester references). For this question the binding is
`region = 'DE'`, `quarter_start = 2026-04-01`, `quarter_end = 2026-06-30`.
The agent supplies values only; it cannot touch the SQL.

**Computation → tables.** The template
[`references/computations/active_customer_revenue_by_region_quarter.sql`](bundle/references/computations/active_customer_revenue_by_region_quarter.sql)
reads exactly the two described tables:
[`tables/billing-invoice-lines.md`](bundle/tables/billing-invoice-lines.md) and
[`tables/crm-customers.md`](bundle/tables/crm-customers.md), joined on
`customer_id`.

**Execution → evidence.** The executor contract
([`references/executors/bigquery-named-parameters.md`](bundle/references/executors/bigquery-named-parameters.md))
runs the template as the caller with named parameters; the attester
reference
([`references/attesters/bq-job-metadata-attester.md`](bundle/references/attesters/bq-job-metadata-attester.md))
is a **non-executable Phase 0 contract stub** describing how a Phase 4
attester would re-read the job by id under its own identity and issue a
fail-closed verdict. The golden receipt specimen (`../golden/receipt.json`)
pins the commitment chain — `publication_id` → `computation_version_id` →
`bq_job_id` — with verdict `UNVERIFIABLE`
(`phase0_no_execution_or_integrity_proof`): nothing was executed, so nothing
can honestly be attested. The `ATTESTED` shape a real Phase 4 run should
produce is in `../golden/expected-phase4-receipt.json`, explicitly
non-normative.

So the trustworthy answer is not a bare number. It is: *the number the
sanctioned computation would produce* (fictional fixture narrative: 1,847
active customers, $4,182,930.55 — no query was run and no displayed value
was independently proven), citable as `[okf:env-0f6c2b8a4d9e4f0a#2]`,
carrying the metric version used, its verifier and freshness, the excluded
legacy definition, the BigQuery job id, and the executed-template hash — all
resolvable from `../golden/identities.json`.

## Notes for reviewers

- `log.md` carries the supersession affirmation (PR #195: exclusion follows
  affirmation; the event lives in the log).
- `supersedes:` and `links:` are §4.1 producer extensions — tolerated, never
  required; their spelling tracks PR #195 / #183 and follows the convention
  if those PRs change.
- Every **non-reserved** `.md` file has parseable frontmatter with a
  non-empty `type` (§11); `log.md` is a reserved §9 file with no
  frontmatter, by design. Unknown `type` values (`Metric`, `Policy`,
  `Attested Computation`, …) are legal; consumers must not reject them.
- Actors use the OKF §7 convention: `human:<id>` for the human sign-offs in
  `verified[].by` and `sources[].author` (a bare id would read as
  machine-confirmed under §5.3 trust tiers, contradicting the narrative).
- No query or attester was executed in Phase 0, and no displayed dollar
  value was independently proven; the attester reference is a non-executable
  contract stub.
- All names, tables, revenue figures, and hosts are fictional.
