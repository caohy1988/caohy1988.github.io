# Slice B live attempt 4 (`chain-gql-b-20260908d`) — every chain stage passed; closeout still not clean

The SSL fix worked. For the first time the whole chain ran end to end under a live GQL engine:

```
approved   bind=BOUND   receipt=VERIFIED   consume=RELEASED   acceptance=MET
engine_admission=OK   engine_proof=PROVEN
```

And yet the run is still **`CHAIN_INCOMPLETE`, `broken_at: window_cleanup`** — because the receipt child produced no
launch journal, so the controller could not bound or inventory what it submitted. That is not a formality: the child
really did submit a BigQuery job that the window never knew about.

**This is not a Slice B success.** No SQL fallback was produced or labelled as Graph.

## What ran

Window 17:43:22Z → ~17:46Z, budget 24 probes / 240 s / 6 consecutive (Haiyuan's raised B1, attempt-only), 10-minute
outer bound, `--gql-evidence-dir evidence/legacy-reconcile`, `--cases approved`.

`sql-substitution` and `declaration-mismatch` were omitted and remain NOT_RUN.

| Stage | Result |
|---|---|
| Prior-cleanup gate | READY (attempt-3 obligation cleared by the operator beforehand) |
| Assignment readiness | reached |
| `engine_admission` | **OK**, `engine_proof: PROVEN` |
| `bind` | **BOUND** |
| `receipt` | **VERIFIED** — `execution_match: MATCH`, receipt id `rcpt-…`, attester artifact hash recorded |
| `consume` | **RELEASED** |
| `acceptance` | **MET** |
| Capacity | deleted, `verified_gone: true` |
| Driver job cleanup | 18/18 journaled jobs terminal, none unresolved |
| Receipt-child journal | **MISSING** → `JOURNAL_DAMAGED` + `LAUNCH_UNJOURNALED` |

## Why the closeout is not clean

The bridge handshake reported `SUPPORTED` with all six guards installed and `bootstrap_imported: true`, the worker was
`registered with the window controller`, and `next_launch()` ran — the journal *directory* was created at 17:45. But
`journal/launch_001.jsonl` was never written, so the guards did not install in the actual receipt child. The child
therefore ran with **no deadline enforcement, no admission bound and no job journaling** while the paid window was
open. It happened to succeed, which is luck, not containment.

### The child's job, found by reconciliation

`evidence/legacy-reconcile/reconcile_receipt_child_chain-gql-b-20260908d.json` lists the platform's own view of
17:41–17:55Z: **20 jobs — 18 driver-journaled, 1 receipt-child, 1 unrelated.**

* `okf_rcpt_2d53caf4a58c9484b2498895_d9ea0bca06dd184d` — DONE, operator identity, submitted 17:45:54Z inside the
  window, absent from the driver's journal. This is the receipt child's own query. Nothing leaked and nothing is
  non-terminal, but the controller never saw it.
* `scheduled_query_6b5cf0c6-…` by `bqaa-otlp-consumer@…` — **unrelated project work**, classified explicitly and left
  alone. Not cancelled, not absorbed into this window's inventory.

> **Superseded 2026-09-08:** the cause below was recorded as unestablished. It has since been root-caused,
> reproduced hermetically and fixed — see `SLICE_B_JOURNAL_ROOT_CAUSE_20260908.md`. In short: the bridge directory was
> relative, the child runs with `cwd=<sdk_root>`, so its `PYTHONPATH` resolved against the SDK checkout and
> `usercustomize` was never importable. The handshake ran with the parent's cwd, which is why it still said
> SUPPORTED. The reproductions below passed because they were given **absolute** paths. This run's
> `CHAIN_INCOMPLETE` outcome is unchanged.

### What is and is not known about the cause

The identical code path — `run_receipt` driven by `ReceiptBridge.runner()`, same interpreter, same SDK entry point,
same cwd — was re-run **hermetically after the window closed and it journals correctly**: `launch_001.jsonl` is
written with `bridge_installed`, and the receipt verifies. Two narrower reproductions (a bare `-c` child, and the real
`run.py --help`) also journal correctly.

So this is not simple miswiring, and `env_injected: []` in the receipt record is a red herring — that field reports
`run_receipt`'s own `env_extra`, not the bridge runner's injected environment, which is merged separately in
`runner()`.

The remaining difference between the reproductions and the failing run is `live=True` (which adds `--live` and
`GOOGLE_CLOUD_PROJECT`) and running inside an open window. **The cause is not established**, and it is deliberately
not guessed at here. Reproducing it would mean either another paid window or exercising the live receipt path against
capacity that currently belongs to another workload, neither of which this pass was authorized to do.

## State left behind

* Capacity: the spike reservation is deleted and verified gone.
* `okf-demo-enterprise` was **kept** (never this run's to delete), and its standing project-wide QUERY assignment was
  **re-created and confirmed ACTIVE** (`assignments/8858510412905008174`) after the window closed.
* `restores_chain-gql-b-20260908d.json` is **outstanding**, so `require_clean_windows` blocks another window until an
  operator clears it. That is correct behaviour and is left for the operator, not self-cleared.

## What this establishes

Under a live Enterprise window with a real GQL engine, the connected chain reaches `acceptance: MET`: graph retrieval
proven, binding verified, receipt verified with an execution match, consumer released. That is the first end-to-end
pass of the chain's stages.

## What it does not establish

It is **not** a clean run and must not be reported as Slice B passing. A chain whose receipt child escapes the
window's containment has not demonstrated the property Slice B exists to demonstrate — that every owned job is
bounded, inventoried and reconciled. One case is not a benchmark, the negative cases are still NOT_RUN, G8 remains
0/9, and no Sep 19 acceptance or pilot claim follows.

## Follow-ups

1. **Root-cause the missing launch journal** before any attempt 5 — the retained artifacts (empty `journal/`,
   handshake record, receipt record, the three hermetic reproductions) are the starting point. Until it is understood,
   every live receipt leg runs unguarded.
2. Consider failing closed: if the parent allocated a launch and the child exits without having journaled
   `bridge_installed`, that is detectable at join time and could refuse before the consumer releases, rather than
   surfacing only as a cleanup obligation afterwards.
3. Clear `restores_chain-gql-b-20260908d.json` once (1) is resolved; clearing must not rewrite this run's
   `CHAIN_INCOMPLETE` outcome.
