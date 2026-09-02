# Intent — BQAA → derived OKF prototype on /rfc/

Status: accepted from Field Brief handoff (Haiyuan, 2026-09-02). Product owner merge remains the live-site gate.

## What

Ship a real clickable prototype under https://caohy1988.github.io/rfc/ that:

1. Takes BQAA observer traces (fixture events, not a fifth source of truth).
2. Converts them one-way into a **derived** OKF v0.2 bundle, labeled demo/derived, never canonical authoring.
3. Compiles that bundle through the existing RFC identity chain (`observation_id` → `snapshot_id` → `publication_id`).
4. Projects the result into the RFC's two stores: Knowledge Catalog (discovery) and BigQuery (serving).
5. Lets an agent retrieve and act with **`context_ref` only** on tool results.

## Why

The live RFC is a document. Phase 0 (`okf-phase0-mvp/`) is files on disk. Reviewers and Haiyuan cannot click the observer→bundle→two-projections→agent-consume path. This slice makes that path visible without changing OKF v0.2 core.

## Constraints (do not break)

- Live RFC: https://caohy1988.github.io/rfc/ — optional profile, **no OKF v0.2 core changes**.
- BQAA is **observer-only**. Traces are not a fifth source of truth and must not mutate authored knowledge. The Phase 0 Cymbal fixture stays authored; the adapter output is a separate derived bundle.
- Identity chain: `observation_id` / `snapshot_id` / `publication_id`. Agent tools emit `context_ref` only. Never emit `concept_version_id`, source paths, principal, or query text in telemetry.
- Prefer extending `okf-phase0-mvp/` over a new stack. Pages home is this repo, tab already at `/rfc/`.
- Label derived/demo, not canonical authoring. Honest about what is fixture vs live GCP.
- Haiyuan is accept/merge. Dual LGTM is agent-complete, not live.

## Out of scope

- Changing OKF v0.2 authoring syntax or required keys.
- Live Knowledge Catalog writes (Phase 2; `kcmd` probes still open). Discovery pane is a **projection view**.
- Live attester / real BigQuery job execution (Phase 4). Receipts stay honest: fixture `UNVERIFIABLE` unless a clearly labeled non-normative Phase-4 shape is shown beside it.
- Merging SDK PRs 468/470, starting the #435 clock, or any new BQAA production job.
- A screenshot mock. The page must be clickable.

## Success

A visitor opens `/rfc/` (or `/rfc/demo/`), runs four beats without leaving the browser, and can see: observer events → derived bundle → two projections → agent consume emitting only `context_ref`. PR lands on `caohy1988/caohy1988.github.io`; Codex + Kimi review on GitHub; Haiyuan merges to make it live.
