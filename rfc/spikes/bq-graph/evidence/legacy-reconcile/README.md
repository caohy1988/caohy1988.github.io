# Legacy window job-cleanup reconciliation — all five openings

Date: 2026-09-08 UTC. Worktree `/Users/haiyuancao/caohy1988.github.io-legacy-reconcile`, branch
`feat/legacy-window-reconcile`, baseline `d002447f54d5d3bad06fdc2fc6cdf7e28f2966fe` (PR47 merged).
Project `test-project-0728-467323`, location `US`. Read-only throughout: `jobs.list` and `jobs.get` and nothing else.

## Verdict

**Job-cleanup reconciliation: RECONCILED for all five openings.** `reservation.require_clean_windows(manifest,
evidence_dir="evidence/legacy-reconcile")` passes against this directory. **The Slice B window gate as a whole is
still BLOCKED** — see "What this does not unblock".

| Window | Owned jobs | All terminal | `verified` | Invocation span (process lifetime) | Source of the exit bound |
|---|---|---|---|---|---|
| `smoke-1` | 1 | DONE ×1 | true | 23:43:43Z .. 23:47:20Z | complete 14-step session log; the submitter was one foreground `bq query` |
| `integration-0007` | 12 | DONE ×12 | true | 00:07:32.984004Z .. 00:09:09.727229Z | the driver's own run record |
| `integration-0009` | 3 | DONE ×3 | true | 00:09:57Z .. 00:11:07Z | safety watcher's first action (runs only after `kill -0` fails) |
| `all-0012` | 36 | DONE ×36 | true | 00:12:38.832828Z .. 00:15:55.901536Z | the driver's own run record |
| `all-0017` | 314 | DONE ×314 | true | 00:17:56.230721Z .. 00:27:33Z | `finished_at` is null (SIGINT); watcher's "reservation already gone" |

366 owned jobs, every one read back DONE under its exact `(project, location, job_id)`. Every listing drained to no
continuation token, no cap, no `unreachable` location; the repeated pass added no reference. All 56 job ids recoverable
from the retained local evidence appear in the journals.

**Corrected after Astra's PR50 first review (P1).** The first pass owned 364 and excluded campaign work outside the
capacity intervals by rule. That was wrong twice over: it dropped two retained pre-open pointer lookups that are these
windows' own setup, and it would have let a post-close continuation that was still RUNNING pass the gate without ever
being read back. Ownership is now bounded by the **invocation**, not by capacity, and nothing is excluded on location
alone. See "How ownership is bounded" below.

## What was actually established

The five openings had no `jobs_<label>.json` at all, so `lifecycle.job_cleanup_verified` had nothing to verify. The
gap was never permissions — an authorized operator `jobs.list` (`allUsers`, `projection=FULL`, no state filter) reads
the whole episode. It was **attribution**: the 2026-09-05 driver stamped a campaign label (`okf_spike`) but no
per-window label, so nothing tied an individual job to an individual opening.

## How ownership is bounded

The unit of ownership is the **invocation**, not the capacity interval. A driver submits before it opens (the
2026-09-05 driver resolves the publication pointer at `run.py@b6e4f09:252`, *before* it stamps `started_at` at L254
and calls `open_window` at L265) and can still be submitting after it closes, since the safety watcher can delete
capacity while the driver's own submissions continue. Capacity says where a job ran; it does not say which invocation
submitted it.

So each window's ownership span is the hull of its recorded capacity interval and its **retained invocation span**,
and three rules apply, in order:

1. A campaign job (the driver's `okf_spike` label, or a reference to one of the spike's six datasets) inside exactly
   one window's ownership span is **owned** by it. Time alone still owns nothing — a job with no campaign signal
   inside the span is `in_span` and blocks.
2. A campaign job inside **another** window's ownership span is excluded to that window. The reservation name cannot
   override this: the spike recreated one name for all five openings.
3. A campaign job outside **every** span may be excluded **only** by a retained record that bounds this window's
   driver process at *both* ends — the driver's own `started_at`/`finished_at`, or a watcher whose teardown runs only
   after `kill -0` on the driver pid fails. Then the process demonstrably did not exist when the job was created.
   With no such two-sided record the job is **unresolved and blocks**, and only an explicit decision naming it can
   assign or exclude it. (`bin/safety_teardown.sh` polls every 15 s, so its stamp places the real exit at or *before*
   it — the span comes out too wide rather than too narrow, which is the safe direction for a cleanup inventory.)

**Correction to the first pass's separation claim.** It said the nearest non-member job sits 38–162 s outside each
boundary. That is false, and the counterexamples are in the retained record: `fccaf7f9-eae1-4be1-9738-f304aa1933bb`
is an `active_publication` lookup at 00:09:56.310Z, **0.69 s** before `integration-0009` opens, and
`8526efa6-c55c-4488-a050-421d3eb580b4` is the same lookup at 00:17:55.499Z, **0.50 s** before `all-0017` opens. Both
are those invocations' first job. They are now owned (by explicit decision citing the driver's ordering) and read back
DONE, which is why the counts moved from 2 → 3 and 313 → 314. The wide separation holds only between *runs*, not
around the recorded open stamps, which are truncated to whole seconds.

Jobs with no campaign signal, plus the two pre-open lookups, are resolved one at a time in
`bin/legacy_window_decisions.json` (58 entries, regenerable by `bin/legacy_window_decisions.py` from
`episode_listing_index.json`):

* **The two pre-open publication-pointer lookups — OWNED** by `integration-0009` and `all-0017` respectively, citing
  `run.py@b6e4f09:252-265`, their sub-second adjacency to the recorded open, and the previous invocation's retained
  `finished_at` 46 s / 120 s earlier.
* **`okf_rcpt_*` receipt work — EXCLUDED.** `okf_request`/`requester` labels, queries over
  `okf_receipt_spike_20260905.orders`, several run by `okf-receipt-restricted@`. A different spike on the same project.
* **`scheduled_query_*` transfers — EXCLUDED.** `bqaa-otlp-consumer@` merging into `bqaa_hero_demo_20260708`, on a
  schedule that runs before and after this episode.
* **Three operator probes inside `all-0017` — OWNED by `all-0017`.** `SELECT 1` / `SELECT 1 AS x` through the bq CLI
  and one `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` capacity read, all inside its interval on its reservation.
* **One capacity read at 00:01:16Z — EXCLUDED.** No window was open; it belongs to no paid opening.

Quiescence was **derived, not asserted** (`reconcile_window.quiescence_probe`): a complete `jobs.list` drain from each
close to the read moment, ~2.5 days, showing nothing attributable after the close, nothing non-terminal left
unresolved, and the silence measured rather than assumed. Each record states its own limit — silence shows submission
stopped, not that a process object is gone. Because rule 3 above leaves post-close campaign work *unresolved* rather
than excluded, such a job is attributable, so a continuation still RUNNING after the close now refuses quiescence and
blocks the window instead of being silently dropped.

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
* **`cost.json` under-counts `all-0017`, and the missing job is the interesting one.** The plan derived 313
  candidates within that span from `cost.json`; the all-users listing shows **314** inside the capacity interval, of
  which 313 are `raincoatrun@gmail.com` and one is `scheduled_query_6b0f5992…` owned by `bqaa-otlp-consumer@`.
  `cost.json` carries no principal column and its count matches the operator's rows exactly, so it was scoped to one
  user; the historical cost accounting never saw a job that ran on the window's Enterprise slots. That transfer is
  excluded (the transfer service owns it) and listed in `reconcile_all-0017.json#/result/excluded`. The journal's 314
  is the operator's 313 inside the interval plus the pre-open pointer lookup `8526efa6…`.
* **The independent Slice B blockers are untouched**: `chain.py` still has no owned Enterprise lifecycle, the SDK child
  bridge is unwired, and no fresh assignment/isolation check has been run. No paid window may open on this evidence
  alone, and none was opened. Haiyuan's separate concrete live authorization remains required.

## Reproducing

```
python3 bin/legacy_window_decisions.py evidence/legacy-reconcile/episode_listing_index.json \
    bin/legacy_window_decisions.json          # reproduces the committed decisions byte-for-byte
python3 bin/legacy_window_plan.py /tmp/stage/plan.json
python3 -m okf_bq_graph.reconcile_window --plan /tmp/stage/plan.json --stage-dir /tmp/stage --live
```

`--live` builds a GET-only transport. `reservation.close_window`, `lifecycle.cancel_journal`, `safety.cleanup` and
`bin/safety_teardown.sh` are mutations and are not imported by the reconciler. No `INFORMATION_SCHEMA` query was run:
that would itself submit a job.

Files: `plan.json` (inputs + source hashes), `reconcile_<label>.json` (full ledger, readbacks, quiescence probe),
`jobs_<label>.json` + `jobs_<label>.cleanup.json` (the gated pair), `episode_listing_index.json` (trimmed drain the
decisions rest on).
