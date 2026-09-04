# Spec — VP punchline strip (v3)

## Goal
~20s strip for VP of BQ. Thesis: **BQ = runtime of KC + OKF.**

## Required punchlines (order fixed)

1. **BigQuery is the runtime of Knowledge Catalog + OKF.** Catalog finds and distributes; BigQuery retrieves deterministically, governs IAM cleanly, and can walk the OKF chain.
2. **Deterministic retrieval from OKF-in-KC.** LookupContext/search surface concepts; they cannot pin-or-fail-stale to a deployment head or join `context_ref` → receipt in SQL. The BQ runtime binds concept → publication → run → receipt.
3. **Easier IAM.** EntryGroup IAM cascades (any `catalogViewer` reads the policy body). BQ runtime: one security domain per deployment, table/dataset grants, caller-delegated auth. Label **RFC / Phase A** where table-level grants are not live.
4. **BigQuery Graph → OKF chain, the easy way.** Observation → Snapshot → Publication (and resolved edges) is queryable as a chain; BigQuery Graph (GA) is the easy path to retrieve that OKF-standard chain. Honesty: this page shows the chain via live SQL/adapter evidence today; Graph is the RFC **optional** projection (relational authoritative) — no invented Graph job id.
5. **Proof from the customer story.** Without BQ runtime, consume agent (`04fa3d56`) said Germany revenue was “verified” from `ok: true`. With a BQ verdict (`f21ee192`): “No. The number is unproven.” (12/12).

## UI / gates
Hero-adjacent strip; meta/og lead with thesis; checker exit 0; node --check; no ATTESTED / BQ_COMMITTED / invented Phase A / invented Graph capture.
