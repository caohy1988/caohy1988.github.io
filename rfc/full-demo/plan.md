# Plan — building the full-version demo

Implement from this file after Haiyuan merges the plan PR. Repo `caohy1988/caohy1988.github.io`;
syncer code lives in the RFC's `toolbox/okf-context` package (location per RFC §04; name is
bikeshed) and is **not** part of this PR. Implementer: Fable 5.1. Reviewers: Codex + Kimi on
GitHub. Do not merge anything below yourself.

## Phase A — `okf-context sync` CLI (needs real GCP)

Deliverable: a CLI that runs steps 1–7 of `spec.md` §1.1 end to end against
`test-project-0728-467323`.

| Item | Detail |
|---|---|
| Language | TypeScript, `kcmd` imported as a library for `ApiContext` and entry patching (RFC §04). Python is acceptable if `kcmd` library import proves unusable; state which in the PR. |
| Input | `--bundle` = the derived bundle produced by `run.py` on PR 474 `main` (label `derived/demo` preserved). `--deployment okf-rfc-demo`. `--entry-group okf-rfc-demo`. `--dataset okf_rfc_demo`. |
| BigQuery DDL | New tables in `okf_rfc_demo`: `publications`, `deployments`, `deployment_heads`, `deployment_heads_history`, `concept_versions`, `snapshot_membership`, `relationship_assertions`, `context_ref_bindings`, `catalog_ownership`. Never touch `agent_events`. |
| Catalog prerequisites | Run the sample `setup.ts` once to register shipped `okf-bundle` + `okf` in the project (today only the older `okf-concept` type exists). Create the profile-owned `okf-context-runtime` AspectType (fields: `publication_id`, `published_snapshot_id`, `managed_by_deployment`, `managed_by_sync_id`). Push the derived bundle with the sample `push.ts` so the syncer has entries to stamp. Leave `okf-derived-germany` (type `okf-concept`) in place, labelled prior. |
| Identities | Reuse `PROFILE.md` hashing exactly as `derived_vectors.py` / `vectors_gen.py` do. Do not invent hashes; assert the CLI reproduces `53bd1651…` for the bundle on record before committing anything. |
| Gate | Second run prints `no-op` and writes nothing. Kill the process between `BQ_COMMITTED` and stamp; rerun completes stamp without a new publication. Removing one concept file removes only the ledger-owned entry. `bq query` over `deployment_heads_history` shows two rows after a deliberate republish of an unchanged snapshot (provenance, not silent). |
| Out | Attester. Scheduler (show the Cloud Run Job YAML only). `sync --from-catalog`. |

## Phase B — BigQuery serve path against real tables

| Item | Detail |
|---|---|
| Retrieve | `okf_retrieve_context` reads `deployment_heads` → `snapshot_membership` → `concept_versions` with `mode: current` excluding superseded. Result shape unchanged from the trace on record (six items, one exclusion, `context_ref`). |
| Pin-or-fail-stale | A `context_ref` bound to a non-head publication returns `FAIL_STALE`; junk returns `FAIL_CLOSED`. Both are exercised in the tape. |
| Attested computation | Still `UNVERIFIABLE`, reason `no-execution`. Do not run SQL under the demo identity and call it attested. |
| History query | The `deployment_heads_history` query that answers story 2 question 4. |
| Join query | `agent_events` ⋈ `context_ref_bindings` ⋈ `publications` producing the story 3 table. v0 of the query (over `agent_events` only) is committed as `rfc/full-demo/sql/sessions_by_context_ref.sql`; Phase B extends it with the join. |
| Gate | Never-emit scan over every tool result: 0 hits. Queries are checked in and their results are checked in as JSON snapshots with the `bq` job id. |

No new observe-agent run. If a consume-side transcript is wanted for beat 5, replay the existing
session `f21ee192` rows; do not pad `agent_events`.

## Phase C — `/rfc/full-demo/` page

| Item | Detail |
|---|---|
| Shape | Static viewer, vanilla JS, RFC tokens, six-beat stepper, deep links `#beat=1…6`. Same honesty chrome as `/rfc/demo/` (browser never calls GCP; identities pinned from CLI). |
| Beat 3 | Two panes: `gcloud dataplex entries lookup … --view=ALL` transcript, and the `04fa3d56` transcript with the sentence "You can trust the number because it is verified" highlighted. Caption: "discovery worked; trust was invented." |
| Beat 4 | The Phase A asciinema tape, with `BQ_COMMITTED` and `CATALOG_STAMPED` as named marks. |
| Beat 6 | The join query and its result table, with the Catalog pin row marked "oldest". |
| Capability matrix | Rendered from `spec.md` §2 as a table with a "shown on beat N" column; rows not shown say "RFC text only". |
| Checker | `rfc/full-demo/tools/check_full_demo.py`: beats present, session ids and publication prefixes match the checked-in snapshots, `ATTESTED` appears only inside the labelled non-normative shape, never-emit list absent from all tool JSON, `okf-derived-germany` labelled prior. |
| RFC wiring | One clause added to the existing Prototype callout on `rfc/index.html` linking `./full-demo/`. No restyle. |
| Gate | Checker exits 0; `node --check` on the page JS; manual six-beat click-through with no console errors. |

## Phase D — recording (after Codex + Kimi dual LGTM on the Phase C PR)

- One asciinema cast of beats 4 → 6 (`okf-context sync` twice, the three serve queries, the join),
  rendered to gif and a ~90 s H.264 mp4 with the join table as the poster frame.
- Keep `okf-bqaa-cli.mp4` as the Observe → Publish → Next-agent tape; do not re-record it.
- Push with `-c http.postBuffer=524288000` and verify `git ls-remote` before `gh pr create`.

## What stays CLI, what needs real GCP, what stays stubbed

| Concern | Answer |
|---|---|
| Stays CLI | `kcmd push` (Catalog), `run.py` (adapter), `okf-context sync` (bridge), `bq query` (serve and join). |
| Needs real GCP | BigQuery DDL/DML for the runtime tables; Catalog aspect-type creation and entry stamping; sample `setup.ts` + `push.ts` for shipped types. All in `test-project-0728-467323`, `us-central1`, dataset `okf_rfc_demo`. |
| Stays stubbed | Attester and `ATTESTED` verdict; scheduler; `sync --from-catalog`; sub-concept policy enforcement (shown as structure only). |
| Never | Re-run the observe agent; pad `agent_events`; rewrite the authored Cymbal fixture; change OKF v0.2 core, `PROFILE.md`, or SDK PR 474; start #435. |

## Order and rough sizing

1. Phase A (largest; the syncer plus GCP prerequisites). Own PR in the toolbox repo; link from here.
2. Phase B queries and snapshots. Small; can start once Phase A tables exist.
3. Phase C page. One PR here. Reviewers: Codex + Kimi.
4. Phase D recording. Follow-up after dual LGTM.

## Risks

| Risk | Mitigation |
|---|---|
| `kcmd` library import is not usable for aspect patching | Fall back to `gcloud dataplex entries update --aspects` from the CLI; note it in the PR. |
| Shipped `okf` AspectType cannot be registered beside the older `okf-concept` type in this project | They are independent types; keep both, label `okf-concept` prior. If Dataplex rejects, use a fresh EntryGroup `okf-rfc-demo-v2`. |
| Same `context_ref` already bound to two publications (`674153c5…`, `53bd1651…`) | `context_ref_bindings` is append-only with `bound_at`; head resolution takes the latest committed binding and the page states the earlier one is historical. |
| Reviewer reads beat 3 as "Catalog is bad" | Beat 3 caption and the matrix's honest-limits line say Catalog's discovery projection is shipped and complete; the runtime sits on it. |
