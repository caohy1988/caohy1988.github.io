# Legacy window job-cleanup reconciliation — all five openings

Date: 2026-09-08 UTC. Worktree `/Users/haiyuancao/caohy1988.github.io-legacy-reconcile`, branch
`feat/legacy-window-reconcile`, baseline `d002447f54d5d3bad06fdc2fc6cdf7e28f2966fe` (PR47 merged).
Project `test-project-0728-467323`, location `US`. Read-only throughout: `jobs.list` and `jobs.get` and nothing else.

## Verdict

**Job-cleanup reconciliation: RECONCILED for all five openings.** `reservation.require_clean_windows(manifest,
evidence_dir="evidence/legacy-reconcile")` passes against this directory. **The Slice B window gate as a whole is
still BLOCKED** — see "What this does not unblock".

| Window | Owned jobs | All terminal | `verified` | Local stop stamp |
|---|---|---|---|---|
| `smoke-1` | 1 | DONE ×1 | true | 2026-09-05T23:46:30Z |
| `integration-0007` | 12 | DONE ×12 | true | 2026-09-06T00:09:09.727229Z |
| `integration-0009` | 2 | DONE ×2 | true | **RETAINED GAP** — none recorded |
| `all-0012` | 36 | DONE ×36 | true | 2026-09-06T00:15:55.901536Z |
| `all-0017` | 313 | DONE ×313 | true | **RETAINED GAP** — none recorded |

364 owned jobs, every one read back DONE under its exact `(project, location, job_id)`. Every listing drained to no
continuation token, no cap, no `unreachable` location; the repeated pass added no reference. All 56 job ids recoverable
from the retained local evidence appear in the journals.

## What was actually established

The five openings had no `jobs_<label>.json` at all, so `lifecycle.job_cleanup_verified` had nothing to verify. The
gap was never permissions — an authorized operator `jobs.list` (`allUsers`, `projection=FULL`, no state filter) reads
the whole episode. It was **attribution**: the 2026-09-05 driver stamped a campaign label (`okf_spike`) but no
per-window label, so nothing tied an individual job to an individual opening.

Window membership is decided here by the **recorded capacity interval**, and it works because the intervals are
cleanly separated in the job stream — the nearest non-member job sits 38–162 s outside each boundary, and the strict
per-window counts (1, 12, 2, 36, 314) reproduce the candidate counts the plan derived independently from `cost.json`.
A job is owned only with a positive campaign signal (the driver's label, or a reference to one of the spike's six
datasets) **and** an instant inside exactly one declared interval. Time alone still owns nothing.

Twenty-nine listed jobs had no such signal and were resolved one at a time in `bin/legacy_window_decisions.json`
(56 entries, regenerable by `bin/legacy_window_decisions.py` from `episode_listing_index.json`):

* **`okf_rcpt_*` receipt work — EXCLUDED.** `okf_request`/`requester` labels, queries over
  `okf_receipt_spike_20260905.orders`, several run by `okf-receipt-restricted@`. A different spike on the same project.
* **`scheduled_query_*` transfers — EXCLUDED.** `bqaa-otlp-consumer@` merging into `bqaa_hero_demo_20260708`, on a
  schedule that runs before and after this episode.
* **Three operator probes inside `all-0017` — OWNED by `all-0017`.** `SELECT 1` / `SELECT 1 AS x` through the bq CLI
  and one `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` capacity read, all inside its interval on its reservation.
* **One capacity read at 00:01:16Z — EXCLUDED.** No window was open; it belongs to no paid opening.

Quiescence was **derived, not asserted** (`reconcile_window.quiescence_probe`): a complete `jobs.list` drain from each
close to the read moment, ~2.4 days, showing nothing attributable after the close, nothing non-terminal left
unresolved, and the silence measured rather than assumed. Each record states its own limit — silence shows submission
stopped, not that a process object is gone.

## Three findings worth carrying forward

1. **Capacity deletion propagates late.** `all-0017`'s reservation is recorded DELETE at 00:27:27.393Z, yet
   `okf_rcpt_cfa80316…` (00:27:56Z), `okf_rcpt_1335b9df…` (00:27:57Z) and `okf_rcpt_612bdaff…` (00:28:05Z) all report
   `reservation_id = …okf-graph-spike-20260905` and `edition: ENTERPRISE` — up to 38 s after. Their immediate siblings
   in the same burst carry no reservation at all, so this is propagation lag, not membership. **A closer that verifies
   capacity absent has not thereby stopped billing to it.**
2. **A `PROJECT`/`QUERY` assignment routes unrelated traffic onto the paid window.** The manifest's
   `mk --reservation_assignment --assignee_type=PROJECT --job_type=QUERY` means every query job in the project ran on
   the spike's Enterprise capacity while a window was open — including `scheduled_query_6b0f5992…`, owned by the
   analytics transfer service, at 00:20:08Z inside `all-0017`. It is excluded from the journal (the transfer service
   owns the job) but it consumed the window's slots. Cost attribution and isolation both need a narrower assignee.
3. **The reservation NAME cannot discriminate between these windows.** `cleanup_manifest.json` records five
   create/delete cycles on the single name `okf-graph-spike-20260905`, so it is shared by all five openings.

## What this does not unblock

* This is **job cleanup only**. Capacity `verified_gone` was and remains a separate predicate.
* These are **reconstructions**, and say so in their own bytes: `reconstructed: true`, evidence sources with SHA-256,
  and a note that they are not the contemporaneous pre-submission journals. No original artifact was overwritten;
  nothing was promoted into `evidence/` itself. `verified` is derived from the readbacks, never handed in.
* Two windows retain a **gap**: `integration-0009` (killed by session teardown) and `all-0017` (SIGINT at 00:24:54Z,
  `finished_at: null`) never stamped their own exit, so their stop moment rests on the platform probe alone. SIGINT is
  when the signal was sent, not when submission stopped, and is deliberately not used.
* **`cost.json` under-counts `all-0017` by one, and the missing job is the interesting one.** The plan derived 313
  candidates within that span from `cost.json`; the all-users listing shows **314**, of which 313 are
  `raincoatrun@gmail.com` and one is `scheduled_query_6b0f5992…` owned by `bqaa-otlp-consumer@`. `cost.json` carries no
  principal column and its count matches the operator's rows exactly, so it was scoped to one user. The historical
  cost accounting therefore never saw a job that ran on the window's Enterprise slots — which is finding 2 showing up
  as a number. The journal's 313 is the operator's 313; the transfer is excluded because the transfer service owns
  that job, and it is listed in `reconcile_all-0017.json#/result/excluded`.
* **The independent Slice B blockers are untouched**: `chain.py` still has no owned Enterprise lifecycle, the SDK child
  bridge is unwired, and no fresh assignment/isolation check has been run. No paid window may open on this evidence
  alone, and none was opened. Haiyuan's separate concrete live authorization remains required.

## Reproducing

```
python3 bin/legacy_window_plan.py /tmp/stage/plan.json
python3 -m okf_bq_graph.reconcile_window --plan /tmp/stage/plan.json --stage-dir /tmp/stage --live
```

`--live` builds a GET-only transport. `reservation.close_window`, `lifecycle.cancel_journal`, `safety.cleanup` and
`bin/safety_teardown.sh` are mutations and are not imported by the reconciler. No `INFORMATION_SCHEMA` query was run:
that would itself submit a job.

Files: `plan.json` (inputs + source hashes), `reconcile_<label>.json` (full ledger, readbacks, quiescence probe),
`jobs_<label>.json` + `jobs_<label>.cleanup.json` (the gated pair), `episode_listing_index.json` (trimmed drain the
decisions rest on).
