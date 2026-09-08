# Slice B live GQL attempt — BLOCKED at window open (2026-09-08)

One live `chain.py --live --engine gql` run was attempted under explicit authorization. **No Enterprise window opened,
no capacity was provisioned, no job was submitted and no spend was incurred.** The attempt is retained here because a
refusal is evidence, and because it found a defect that would have made a *successful* open unsafe.

Outcome: **BLOCKED**. This is not a GQL result. Slice B remains unrun; it is not a promotion bar either way.

## What was attempted

```
python3 -m okf_bq_graph.chain --live --engine gql \
  --gql-window chain-gql-b-20260908 --gql-window-minutes 10 \
  --gql-manifest evidence/cleanup_manifest.json \
  --gql-evidence-dir evidence/legacy-reconcile \
  --gql-max-slots 100 --cases approved --out evidence/chain
```

Started 2026-09-08T14:13:33Z, refused 14:13:39Z, exit 1. Case `approved` at C=1 was selected; `sql-substitution` and
`declaration-mismatch` were omitted and are **NOT_RUN**, never implied to pass.

## Preflight (all gates passed before the attempt)

| Gate | Result |
|---|---|
| Assignment/reservation isolation, US + us-central1 | No reservations, assignments or capacity commitments exist. Nothing peer to preserve. |
| Principal roles | `roles/owner`, `roles/bigquery.jobUser`, `roles/bigquery.dataViewer`, `roles/bigquery.connectionAdmin` |
| APIs | `bigquery`, `bigqueryreservation`, `bigquerydatapolicy`, `dataplex` enabled |
| SDK pin | interpreter at `google-cloud-bigquery==3.45.0`; SDK checkout head `6719eb5` == `SDK_PIN` |
| `require_clean_windows(manifest, evidence_dir="evidence/legacy-reconcile")` | **PASS** (all five legacy labels verified) |
| ReceiptBridge preflight + handshake | **SUPPORTED** — 7/7 source seams, 6/6 guards installed in the child, `enable_user_site` true |
| Hermetic suite at the pinned SDK | 761 passed |
| Checkout | clean at `1f27717` |

The hermetic suite had previously only ever been run against the *installed* `3.40.1` (README, "What Slice A does not
establish"). It was re-run here against the pinned `3.45.0` and is green, which closes that specific revalidation gap.
It does not make any live claim.

## Why it was refused

```
gql window refused: WindowRefused: OPEN_FAILED:
RuntimeError: job cleanup is unverified for all-0012; reconcile its journal before opening another
```

`all-0012`'s cleanup **is** verified — in `evidence/legacy-reconcile/`, where PR50 reconciled it, and where this run
was explicitly pointed with `--gql-evidence-dir`. The refusal is a directory disagreement inside the lifecycle, not an
outstanding obligation:

* `ChainWindow.preflight()` gates with `require_clean_windows(..., evidence_dir=self.cfg.evidence_dir)`
  (`chain_window.py:196`) — reads `evidence/legacy-reconcile/`, passes.
* `ChainWindow.open()` then calls the injected opener, and `reservation.open_window()` re-gates with
  `require_clean_windows(m, exclude=label)` (`reservation.py:181`) — **no `evidence_dir` parameter exists**, so it
  falls back to `Path(MANIFEST).parent` = `evidence/`, finds no `jobs_all-0012.json` there, and refuses.

So `--gql-evidence-dir` is honoured by the controller and silently ignored by the opener. With that flag set to
anything other than the manifest's own directory, a window can never open, whatever the true cleanup state is.

## The more serious half: the detached safety watcher

`evidence/watcher_chain-gql-b-20260908.jsonl` records all three watcher attempts failing with:

```
FileNotFoundError: [Errno 2] No such file or directory: 'evidence/jobs_chain-gql-b-20260908.json'
```

`safety.cleanup()` hardcodes `f"evidence/jobs_{label}.json"` (`safety.py:25`). The detached watcher is spawned with a
label only, so it resolves the journal against a directory the window never used. **Had the open succeeded**, the
independent closer would have deleted capacity while reporting every owned job as unreadable, attempting no
cancellation at all — precisely the "capacity deletion is not job cleanup" failure B3 exists to prevent. The refusal
was therefore protective in effect, though not for the reason it gave.

This is why the attempt was not retried against the default evidence directory to "get around" the gate: the same
plumbing gap that blocks the open is what makes a non-default evidence dir unsafe to run under.

## State after the attempt (verified)

* `evidence/cleanup_manifest.json` — **unmodified** (git-clean). The gate raised before any window row was appended.
* No reservation, no assignment, no capacity commitment created; `ownership_precheck` recorded
  `present: false, listing_ok: true`.
* No query, load or dry-run job submitted. Zero incremental spend.
* `window_chain-gql-b-20260908.json` closes with `clean: false`, `close_reason: open_failed`. Its `window_close.error`
  is `ValueError: unknown reservation window` — the correct consequence of closing a window that never opened, not an
  unresolved capacity obligation.
* `jobs_chain-gql-b-20260908.{json,cleanup.json}` — an empty journal and a `verified: true` receipt over zero jobs.
  `job_cleanup_verified("chain-gql-b-20260908", ...)` is True, so this attempt leaves no obligation blocking a later
  window. `require_clean_windows` still passes for every label.
* `evidence/cleanup_manifest.lease` is a leftover `flock` artifact of the refused run; the lock is released with the
  process, so it blocks nothing. It is gitignored rather than committed.

## What this does and does not establish

Establishes: the receipt bridge handshake is SUPPORTED at the pinned SDK on a user-site-enabled interpreter; the
hermetic suite is green at the pinned `3.45.0`; the PR50 receipts satisfy the gate they were built for; and the
evidence-directory plumbing is incomplete in two places.

Establishes nothing about GQL. No live graph query ran. No SQL fallback was produced or labelled as Graph. G8 remains
0/9. Nothing here bears on the 2026-09-19 checkpoint, and no pilot or acceptance claim follows from it.

## To unblock (needs a decision, not just a patch)

1. **Thread the evidence directory through the lifecycle** — `open_window(..., evidence_dir=None)` and an
   `evidence_dir` for `safety.cleanup()`/the watcher spawn, defaulting to today's behaviour. Three strict-`xfail`
   tests in `tests/test_reservation.py` pin both halves, including that naming a directory waives nothing. Editing
   `okf_bq_graph/reservation.py` was blocked by this session's permission policy, so the fix is specified and tested
   but not applied.
2. **Or publish the reconciled receipts into `evidence/`** and run with the default directory, which is the step
   `require_clean_windows`'s own docstring anticipates ("before anyone decides to publish it into `evidence/`"). This
   needs no code change and makes all three components agree on one directory, but it moves PR50 artefacts that were
   deliberately staged separately, so it is a reviewer's call rather than a runner's.

Option 1 is the better fix: option 2 leaves `--gql-evidence-dir` still broken for the next caller.
