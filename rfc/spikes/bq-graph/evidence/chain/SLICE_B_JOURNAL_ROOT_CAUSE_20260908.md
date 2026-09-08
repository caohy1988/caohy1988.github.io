# Root cause: why the live receipt child wrote no launch journal — and the fail-closed that follows

Attempt 4 (`chain-gql-b-20260908d`) released a `VERIFIED` receipt from a child that had **no deadline, no admission
bound and no journal**. The cause is now established, reproduced hermetically, and fixed. No live window was opened
for this investigation.

## The bug

`ReceiptBridge.__init__` stored its directory as given:

```python
self.dir = Path(directory)          # not resolved
```

`chain.open_gql_window`/`main` construct that directory from the CLI's `--out`, which defaults to the **relative**
`evidence/chain`, so the bridge directory was `evidence/chain/receipt-bridge/<label>`. The bridge exports that path to
the child as `PYTHONPATH`, and the launch journal path with it.

`run_receipt` launches the SDK example with **`cwd=<sdk_root>`**. In that child, the relative `PYTHONPATH` entry
resolved against the SDK checkout — a directory that does not exist. So `usercustomize` was never importable,
`okf_window_bridge.install()` never ran, no guard was installed, and no journal was written. Nothing was created under
the SDK checkout either, which is why there was no stray directory to notice: the import simply failed silently.

That is also why the SDK's own work still succeeded. The bridge is transparent when absent; the child just ran
unguarded.

## Why the handshake said SUPPORTED anyway

`handshake()` ran its probe with `subprocess.run(...)` and **no `cwd`**, so the probe inherited the *parent's* cwd —
the spike directory, where the relative path resolves perfectly. The handshake therefore validated an environment the
real child never ran in. It reported all six guards installed and `bootstrap_imported: true` for the very run whose
child never imported the bootstrap at all.

A preflight that does not reproduce the child's working directory proves nothing about the child.

## Hermetic reproduction

`tests/test_receipt_window.py::test_a_relative_bridge_directory_still_reaches_a_child_with_a_different_cwd`
constructs the bridge exactly as `chain.py` did — a relative `evidence/chain/receipt-bridge/...` — and launches with
`cwd=<sdk_root>`. Before the fix this reproduces the live failure exactly: handshake `SUPPORTED`, child
`bridge_imported: False`, **zero journal files**. Side-by-side, an absolute directory journals correctly, which is why
the three post-run reproductions in `SLICE_B_RUN_D_20260908.md` all passed — they had been given absolute paths.

## Fixes

1. **`self.dir = Path(directory).resolve()`.** The bridge no longer depends on the launcher's cwd. This is the defect.
2. **`handshake(cwd=...)`, defaulting to the SDK root**, and `chain.py` passes `a.sdk_root` explicitly. The probe now
   runs where the receipt child runs, so a false SUPPORTED of this shape cannot recur.
3. **`ReceiptBridge.containment(since=...)`** — every launch the parent allocated must have journaled
   `bridge_installed`. Its absence means that child had no deadline, no admission bound and no journal.
4. **Fail closed before release.** `consume()` takes the containment result and refuses on it; `accept()` records an
   uncontained child as **NOT_REACHED**, not WRONG — a containment outage is unproven, not a contradicted
   expectation. The chain therefore cannot reach `consume=RELEASED` / `acceptance=MET` on an uncontained receipt, as
   attempt 4 did.

`containment(since=...)` is scoped to the launches of the current invocation, so one case's failure is not charged to
a later case in the restricted suite.

## Tests

* the relative-directory reproduction above (the root cause);
* the handshake probes the child's cwd;
* a launch with no `bridge_installed` is reported uncontained, while a bridge with no launches is trivially contained
  — an absent launch is not an accusation;
* `since` scopes the claim to this invocation;
* **happy path unchanged**: a contained receipt still `RELEASED`, and a run with no bridge behaves exactly as before;
* an uncontained child is `REFUSED` before the number is released, carrying no `display` figure;
* an uncontained `approved` case is `NOT_REACHED` rather than `WRONG`.

Hermetic suite at the pinned `google-cloud-bigquery 3.45.0`: **773 passed**.

## End-to-end check, offline

Rebuilding attempt 4's exact configuration — relative `evidence/chain/...` bridge directory, child launched with
`cwd=<sdk_root>` — now gives `handshake: SUPPORTED`, `journals: ['launch_001.jsonl']`, `contained: True`,
`receipt verdict: VERIFIED`, `consume decision: RELEASED`. Before the fix the same configuration produced no journal
at all.

## What this does not change

Attempt 4 remains `CHAIN_INCOMPLETE`. It is not retroactively a pass: its receipt really was produced by an
uncontained child, and its `okf_rcpt_…` job really was outside the window's inventory. This fix means a *future* run
cannot release on that footing — it does not re-score the run that did.

`restores_chain-gql-b-20260908d.json` is still **outstanding** and untouched, so the gate still blocks another window.
No attempt 5 was run and none should be until an operator clears that obligation deliberately.
