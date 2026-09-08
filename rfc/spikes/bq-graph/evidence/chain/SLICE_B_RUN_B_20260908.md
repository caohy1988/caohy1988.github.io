# Slice B live GQL, second attempt (`chain-gql-b-20260908b`) — window opened, chain still NOT_RUN

The evidence-directory fix worked: this window **opened**, ran, closed clean and reconciled every job. The chain's
`approved` case still never executed, because assignment readiness was not reached inside the authorized probe budget.

Outcome: **BLOCKED**, for a new and precisely bounded reason. This is **not** a Slice B chain success and not a GQL
chain observation. No SQL fallback was produced or labelled as Graph.

## Timeline (all times UTC, 2026-09-08)

| At | Event |
|---|---|
| 16:30:40 | `preflight_ok`, 10 minutes granted. The prior-cleanup gate passed against `evidence/legacy-reconcile/` — the refusal that blocked attempt 1 is gone. |
| 16:30:49 | Enterprise reservation created (baseline 0, autoscale max 100, no idle borrowing). |
| 16:30:52 | QUERY assignment created, `state: ACTIVE`. |
| 16:30:59 → 16:32:13 | Probes 1–8 fail: `500 BigQuery Graph queries require a reservation with Enterprise or Enterprise Plus edition`. |
| 16:32:25 | Probe 9 **succeeds** — job `okf_graph_chain-gql-b-20260908b_29accf58…`. |
| 16:32:36, 16:32:48, 16:32:59 | Probes 10, 11, 12 succeed. |
| 16:32:59 | Probe budget exhausted at 12 attempts / 120 s with **4** consecutive successes; 6 are required. `ASSIGNMENT_NOT_READY`. |
| 16:33:05 / 16:33:09 | Assignment and reservation deleted. |
| 16:33:15 | `capacity_close verified_gone: true`; window `CLOSED_VERIFIED`, `clean: true`. |

Window open to close: **2 m 29 s**, against a 10-minute cap.

## Why it stopped

The assignment was `ACTIVE` at 16:30:52 but Graph queries were not admitted until 16:32:25 — roughly **93 seconds of
propagation** before the Enterprise edition took effect for GQL. The authorized budget is 12 probes across 120 seconds
requiring six consecutive successes (plan B1). Propagation consumed 8 of the 12 probes, so only 4 remained. At the
observed ~10.4 s interval, six consecutive successes needed about 156 seconds end to end; the budget allows 120.

This is a budget-versus-latency mismatch, not a capability failure. **Retrying under the identical budget would spend
money to reproduce the same result**, since the shortfall is structural.

## What this does establish

* **The option-1 fix works end to end.** The window opened past the gate that refused attempt 1, and
  `evidence/legacy-reconcile/watcher_chain-gql-b-20260908b.jsonl` records the detached watcher reporting
  `verified_gone: true, jobs: [], errors: []` — no `FileNotFoundError`. Attempt 1's watcher failed all three tries
  because it resolved `evidence/jobs_<label>.json`. The safety-critical half is confirmed against live capacity.
* **GQL admission genuinely works** under an owned Enterprise window against the existing property graph: four probe
  queries executed and returned job IDs. That is an admission observation only.
* **Closure is complete.** 12/12 journaled probe jobs verified terminal, `jobs_unresolved: []`, `restores_failed: []`,
  `workers_unjoined: []`, capacity `CLOSED_VERIFIED`, and `require_clean_windows` still passes, so this window leaves
  no obligation blocking a later one.

## What it does not establish

The chain's `approved` case **NOT_RUN**: no GQL retrieval, no SDK synthetic computation, no enforced consumer, no
receipt leg. `sql-substitution` and `declaration-mismatch` remain NOT_RUN. Four successful probe queries are not a
connected chain and are not a benchmark. G8 remains 0/9. Nothing here bears on the 2026-09-19 checkpoint, and no
pilot or acceptance claim follows.

## Cost

One Enterprise reservation held 2 m 29 s at baseline 0 with autoscale ≤100, plus 12 small probe queries reading
existing data. Well inside the ~$2 authorized envelope. Billing export lag means the charged figure stays PROVISIONAL.

## To unblock — needs authorization, not a patch

Plan B1 caps assignment probes at **12 within 120 seconds**, and this run consumed exactly that. Raising the budget is
therefore a decision for Haiyuan, not a runner's call, even though it is a one-line configuration change:

* Suggested: **24 probes across 240 seconds, still requiring six consecutive successes.** That keeps the readiness
  criterion untouched and only allows for observed propagation. The window's own 10-minute deadline remains the
  outer bound, so the paid envelope does not grow.
* One observation of ~93 s propagation is not a distribution. A second attempt could still miss if propagation is
  slower; the budget should be sized with margin rather than to the single sample.

Until that is authorized, Slice B stays BLOCKED and no further window should be opened.
