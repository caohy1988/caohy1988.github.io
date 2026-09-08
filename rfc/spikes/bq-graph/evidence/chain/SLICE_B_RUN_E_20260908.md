# Slice B live attempt 5 (`chain-gql-b-20260908e`) — `CHAIN_CONNECTED`, clean closeout

The fifth attempt is the first to close cleanly. Every stage passed **and** the receipt child stayed inside the
window's containment, so the run has no outstanding obligation and no job outside its inventory.

```
approved   bind=BOUND   receipt=VERIFIED   consume=RELEASED   acceptance=MET
engine_admission=OK   engine_proof=PROVEN
verdict=CHAIN_CONNECTED   broken_at=None
```

## What ran

Window 18:32:58Z → 18:35:40Z (**2 m 42 s** of a 10-minute cap). Budget 24 probes / 240 s / six consecutive
(Haiyuan's raised B1, attempt-scoped — not a Sep 19 threshold). `--gql-evidence-dir evidence/legacy-reconcile`,
`--cases approved`, `--gql-max-slots 100`, Acme read-only.

`sql-substitution` and `declaration-mismatch` were omitted and remain **NOT_RUN**.

## The difference from attempt 4: containment

```json
"containment": {"contained": true, "uncontained": [], "reason": null,
                "launches": [{"invocation": "chain-gql-b-20260908e-001-096418b6",
                              "bridge_installed": true,
                              "journal": "/Users/…/evidence/chain/receipt-bridge/…/journal/launch_001.jsonl"}]}
```

The journal path is now **absolute**, the child imported the bootstrap, and `bridge_installed` was journaled. As a
direct consequence the controller **adopted** the child's own query into the window's inventory:

```
"adopted_jobs": ["okf_rcpt_b647dd8a20992ef719e6d921_8618317e23a42ab9"]
```

In attempt 4 that same job existed on the platform and the window never knew about it.

## Closeout

| Check | Result |
|---|---|
| `capacity_verified_gone` | true — `CLOSED_VERIFIED` |
| `jobs_total` / `jobs_unresolved` | 7 tracked at close / **none unresolved** |
| Cleanup receipt | `verified: true`, 18/18 journaled jobs verified DONE |
| `worker_obligations_outstanding` | **[]** |
| `workers_unjoined` | **[]** |
| `restores_failed` / `restores` outstanding | **[]** / **[]** |
| `require_clean_windows` after the run | **CLEAN** — this window blocks no future one |

## Independent reconciliation

`evidence/legacy-reconcile/reconcile_identity_chain-gql-b-20260908e.json` — a project-scoped `jobs.list` over
18:30–18:45Z returns **19 jobs**:

* **18 window-journaled**, all DONE, all under the operator identity — including the adopted receipt-child query.
* **0 operator jobs outside the journal.** This is the property attempt 4 failed.
* 1 unrelated `scheduled_query_…` under the `bqaa-otlp-consumer` service account — different principal, classified
  explicitly, never cancelled and never absorbed into this window's inventory.

`same_requester=SAME` for the graph leg; scope limit is one listing at one instant, project-scoped.

## Capacity hygiene

The spike reservation was created inside the window and deleted with verified readback. `okf-demo-enterprise` was
**kept** — it was never this run's to delete — and its standing project-wide QUERY assignment was re-created and
confirmed **ACTIVE** (`assignments/442937817540808812`) after the window closed.

## What this establishes

One connected chain, executed live: GQL retrieval proven under an owned Enterprise window, declaration bound to the
executed publication, a verified receipt produced by a **contained** child, a consumer that released on it, and a
window that closed with every owned job terminal, inventoried and reconciled — capacity deletion *and* job cleanup
*and* worker/restore obligations all clear.

## What it does not establish

One `approved` case at C=1 is **not** a benchmark and not an envelope. The negative cases are NOT_RUN, so nothing here
speaks to authorization refusals or substitution detection. G8 remains 0/9. This is not a 2026-09-19 acceptance, not
pilot validation, and not a promotion bar. n=1 stays n=1: no percentiles, no throughput claim.

The earlier attempts are not rewritten by this one — attempts 1–4 keep their recorded outcomes, and attempt 4 remains
`CHAIN_INCOMPLETE`.
