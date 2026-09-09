# Plan — FS-1, the hermetic sampled request-to-consumer runner, and what it hands to FS-2

Status: implementation sequencing for slice FS-1 of `plan-sqlchain-fact-select.md`. Offline only. No dates, no
staffing claim, no spending authorization. Intent in `intent-sqlchain-consumer-fs1.md`; the contract in
`spec-sqlchain-consumer-fs1.md`. Nothing below fills a cell, measures a latency or accepts a threshold.

## What this slice changes and what it does not

| Item | Before | After FS-1 |
| --- | --- | --- |
| Consumer runner | none (`chain.py` runs each case once; `benchmark.py` stops at retrieval) | `okf_bq_graph.consumer_run`, dry-run and hermetic modes, no `--live` |
| Consumer cells `sqlchain_forced_c1` / `_c5` | `INCOMPLETE`, `NOT_IMPLEMENTED`, 0 of 20 | `INCOMPLETE`, `RUNNER_HERMETIC_ONLY`, 0 of 20; retained hermetic runs listed by id, no number |
| `live_precheck` on the selection | a contract, not implemented | implemented offline as `admit_live` (expiry, `FACTS_DRIFTED`, `OK` with the bound digest); not run live |
| Validity window | recorded | a driver refusal (`VALIDITY_WINDOW`) in both modes |
| Predeclared refusal (`f_revenue`) | not exercised on a sampled path | one probe per cell, expected `REFUSED` at bind, SDK never invoked |
| Row-level check of the vendored manifest | digest recomputation only | plus a row-based oracle reproducing `400` (January) and `515` (January–February) |
| Consumer sampling budget | none declared | `budget.consumer_sampling` declared, `DECLARED_NOT_SPENT` |
| `live_materialization` / `historical_chain_equivalence` | `UNVERIFIED` / `UNPROVEN` | unchanged |
| Cost cells, thresholds | five `UNMEASURED`, all PROPOSED | unchanged |

## Steps, in commit order

1. **Driver and tests together.** `consumer_run.py` with the gates (§3 of the spec), the row oracle (§4),
   `admit_live`, the attempt loop reusing `chain.governed`, `chain.pick_computation`, `chain.declaration`,
   `chain.bind`, `chain.run_receipt` and `chain.consume` unchanged, the per-cell pool, the attempt and run records
   (§5–6). `tests/test_consumer_run.py` written against the spec before the module fills in; SDK- and Acme-dependent
   tests skip when a checkout is absent so the suite stays offline-green anywhere.
2. **Plan and card honesty.** `budget.consumer_sampling` and its validation; `live_precheck` wording;
   `refusal_reasons` → `RUNNER_HERMETIC_ONLY`; `_consumer_cell` with `hermetic_runs`; `project_budget` note;
   `render_markdown`; regenerate `plan.json` / `baseline.md`; update the tests that asserted `NOT_IMPLEMENTED`.
3. **Retained hermetic evidence.** One `--hermetic` campaign over both cells at the predeclared 2 + 20 plus a probe
   each, committed under `evidence/consumer/` with every diagnostic; the card cites it by id.
4. **Surfaces.** The wording in spec §9 on the story, the pack spec, the landing page, the detailed RFC, the
   Knowledge Publications plan and the spike README, with the surface tests extended.
5. **Suite, PR, vault.** Full offline suite green under the Homebrew `python3.13`; PR opened against `main`, not
   merged; Ship/builds and Ship/rfc notes filed.

## Budget block declared here and not spent

`budget.consumer_sampling` in `fixtures/sql_baseline.json`:

| Field | Value | Why |
| --- | --- | --- |
| `state` | `DECLARED_NOT_SPENT` | hermetic mode submits no job; a spent state needs a live campaign record |
| `consumer_max_bytes_billed_gib` | 8 | the consult's ~5–6 GiB estimate for 2 + 20 attempts at C=1, receipt-leg child jobs included, with headroom; inside the 64 GiB campaign ceiling |
| `consumer_max_usd` | 0.05 | 8 GiB at the declared $6.25 per TiB is about $0.049; inside the $0.50 campaign ceiling |
| `consumer_max_wall_seconds_per_cell` | 900 | the campaign's per-cell ceiling, not widened |
| `consumer_max_wall_seconds_total` | 3600 | the campaign's total ceiling, not widened |

The existing 64 GiB / $0.50 block was declared for the retrieval cells; this block is inside it and separate from
it, so a consumer campaign cannot draw silently on the retrieval allowance. C=5 gets no separate line until C=1
completes (the fact-select plan's rule), and FS-3 (restricted identity) needs its own.

## What FS-2 takes from this slice, unchanged

- The gate order and codes, with `admit_live` called before the first attempt against a real full-schema,
  full-row readback canonicalised as `okf-fact-content/1`; `FACTS_DRIFTED` stops the campaign with no cell filled.
- The attempt record shape, with `receipt.job` and `job_times` filled from the SDK's live diagnostic and a real job
  identity read back per job (the chain's `same_requester` rule, including the receipt leg's child jobs).
- The probe: one `f_revenue` attempt per cell, expected `REFUSED` at bind, still with the SDK never invoked.
- The verdict rule, plus the live-only conditions: every job on-demand by job-level override, every job's identity
  known, the ledger inside `consumer_sampling`, the campaign before the materialization expires or after a recorded
  reload under the same digest.

What FS-2 must add and this slice does not pretend to: the readback itself, the BigQuery client and its window
gate, the ledger, the routing guard, the job inventory, and the owner's paid authorization.

## Reopen conditions

- The SDK example changes its hermetic runner or its case set at a new pin: the runner's `SDK_PROVENANCE` gate
  refuses until the pin and the vendored artifacts are re-selected together.
- The materialization expires before FS-2 runs: reload under the owner's gate, same digest, new load job on the
  selection; the hermetic runs stay valid because they never read it.
- A hermetic run is ever cited as a latency or a cost: that is a documentation defect, not evidence; the record's
  `claims.does_not_establish` is the reference.
