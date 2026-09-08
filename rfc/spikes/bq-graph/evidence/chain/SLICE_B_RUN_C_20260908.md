# Slice B live attempt 3 (`chain-gql-b-20260908c`) — GQL admission PROVEN, chain INCOMPLETE

The raised probe budget worked: the window reached assignment readiness, **live GQL admission was proven**, and the
`approved` case bound successfully. The chain then broke at the receipt leg, and the run closed with an **outstanding
cleanup obligation that now blocks further windows**.

Verdict as recorded: **`CHAIN_INCOMPLETE`, `broken_at: window_cleanup`**. This is not a Slice B success. No SQL
fallback was produced or labelled as Graph.

## What ran

```
--live --engine gql --gql-window chain-gql-b-20260908c --gql-window-minutes 10
--gql-evidence-dir evidence/legacy-reconcile --gql-max-slots 100
--gql-probe-attempts 24 --gql-probe-seconds 240 --cases approved
```

Window 17:12:18Z → 17:15:18Z (3 m 00 s of a 10-minute cap). Probe budget raised to 24/240 s by Haiyuan for this
attempt only; six consecutive successes still required, and it is **not** a Sep 19 acceptance threshold.

## Stage by stage

| Stage | Result |
|---|---|
| Prior-cleanup gate | PASS against `evidence/legacy-reconcile/` |
| Assignment readiness | **reached** — the 24/240 s budget covered the propagation that exhausted attempt 2's 12/120 s |
| `engine_admission` | **OK**, `engine_proof: PROVEN` — live GQL, no fallback |
| `bind` | **BOUND** — declared type, `file_sha256` (graph == sdk_bytes == sdk_manifest), freshness FRESH, lifecycle, parameters and `not_executed_by_graph` all OK |
| `receipt` | **UNVERIFIABLE** — child exited 1, no diagnostics |
| `consume` | **REFUSED** — the consumer correctly refused to release an unverifiable receipt |
| `acceptance` | **NOT_REACHED** |
| Capacity | deleted and `verified_gone: true`, `CLOSED_VERIFIED` |
| Job cleanup | 19/19 journaled jobs terminal, `jobs_unresolved: []` |
| Worker/restore obligations | **OUTSTANDING** — see below |

`sql-substitution` and `declaration-mismatch` were omitted and remain NOT_RUN.

## Why the receipt child failed

`stderr_tail` shows the child died in the SDK broker's identity call:

```
urllib.request.urlopen("https://oauth2.googleapis.com/tokeninfo?access_token=" + creds.token)
urllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
unable to get local issuer certificate>
```

This is an **environment defect in the runner's interpreter, not a product defect**. The interpreter reports
`ssl.get_default_verify_paths() -> cafile: None, capath: None`: a python.org framework build whose
`Install Certificates.command` was never run. `certifi` is present, so `requests` and `google-auth` (which use it)
worked all through the driver — but the broker's identity check goes through stdlib `urllib`, which has no trust
store here. Verified fix: with `SSL_CERT_FILE=$(python -c 'import certifi;print(certifi.where())')` the same call
returns HTTP 400 (reached Google, token rejected as expected) instead of failing TLS.

The child died before constructing a BigQuery client, which is why it never wrote a launch journal.

## The outstanding obligation

```
receipt_child:JOURNAL_DAMAGED:.../journal/launch_001.jsonl  - a launch journal the parent allocated does not exist
receipt_child:LAUNCH_UNJOURNALED:chain-gql-b-20260908c-001-4c1c735f - a launch produced no journal record at all:
                                                                     its submissions are unknown
```

`require_clean_windows` now refuses:

```
resource restoration is outstanding for chain-gql-b-20260908c;
clear restores_chain-gql-b-20260908c.json before opening another
```

**This is the system behaving correctly.** An absent journal is not an empty inventory, so the child's submissions
are unknown and another paid window is prohibited until that is reconciled.

### Read-only reconciliation of the unknown submissions

`evidence/legacy-reconcile/reconcile_receipt_child_chain-gql-b-20260908c.json` answers the question against the
platform rather than assuming it: a project-scoped `jobs.list` over 17:10–17:25Z (widened either side of the window)
returns **19 jobs, all 19 already in the driver's journal, all DONE, all under the operator identity, zero unknown**.
No job is attributable to the receipt child, which matches its observed failure point.

Scope limit: one listing at one instant, project-scoped. It bounds the risk; it does **not** clear the obligation.
Clearing `restores_chain-gql-b-20260908c.json` unblocks paid windows and is the operator's decision, not the
runner's — so the obligation is left open and no attempt 4 was started.

## What this establishes

Live GQL admission inside an owned Enterprise window is **proven**, with the graph binding verified byte-for-byte
against the SDK manifest, and the consumer correctly refusing to release on an unverifiable receipt. The raised probe
budget resolved attempt 2's blocker.

## What it does not establish

No completed chain: no verified receipt, no released consumer result, no acceptance. One admitted case is not a
benchmark and says nothing about the omitted negative cases. G8 remains 0/9. No Sep 19 acceptance or pilot claim.

## To unblock attempt 4 — two items, both for Haiyuan

1. **Clear the reconciled obligation.** The evidence above supports closing it; the decision is the operator's.
   Closing it must not rewrite this run's `CHAIN_INCOMPLETE` outcome.
2. **Fix the runner's trust store** before relaunching — export `SSL_CERT_FILE` (and `REQUESTS_CA_BUNDLE`) to
   certifi's bundle, or run the framework Python's `Install Certificates.command`. No product change is needed.

Worth considering separately: the bridge handshake proves the SDK seams and the installed guards before any paid
window opens, but not that the child's stdlib TLS trust store is usable. A one-line preflight would have caught this
without spending a window. That is a suggestion, not a change made here.
