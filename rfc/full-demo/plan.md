# Plan — building the full-version demo

Implement from this file after Haiyuan merges the plan PR. Repo `caohy1988/caohy1988.github.io`;
syncer code lives in the RFC's `toolbox/okf-context` package (location per RFC §04; name is
bikeshed) and is **not** part of this PR. Implementer: Fable 5.1. Reviewers: Codex + Kimi on
GitHub. Do not merge anything below yourself.

v1 direction, restated so no phase contradicts it: **bundle on disk → BigQuery commit → Catalog
stamp**, run by an external CLI. Catalog → BigQuery import is future work and appears nowhere below
as a deliverable.

## Phase A — `okf-context sync` CLI, identities, and shipped Catalog types (needs real GCP)

Deliverable: a CLI that runs steps 1–7 of `spec.md` §1.1 end to end against
`test-project-0728-467323` under the identities of `spec.md` §1.3.

| Item | Detail |
|---|---|
| Language | TypeScript, `kcmd` imported as a library for `ApiContext` and entry patching (RFC §04). Python is acceptable if `kcmd` library import proves unusable; state which in the PR. |
| Input | `--bundle` = the derived bundle produced by `run.py` on PR 474 `main` (label `derived/demo` preserved). `--deployment okf-rfc-demo`. `--entry-group okf-rfc-demo`. `--dataset okf_rfc_demo`. No `--from-catalog` flag in v1. |
| Identities (setup step, human-run once) | Create service accounts `okf-setup`, `okf-sync-writer-okf-rfc-demo`, `okf-runtime-reader`. Grant exactly the resource-specific bindings in `spec.md` §1.3: project-level type/group creation for setup only (time-boxed); `entryTypeUser` on `okf-bundle` and `aspectTypeUser` on `okf` and `okf-context-runtime` for the sync writer; `catalogEditor` on the one EntryGroup; **table-level** `dataEditor` on the nine runtime tables (no dataset grant, so `agent_events` is unreachable); custom role with only `dataplex.projects.search` at project level for the reader; `serviceAccountTokenCreator` per SA for the operator. Record every `gcloud … add-iam-policy-binding` / `bq add-iam-policy-binding` in the tape. |
| BigQuery DDL (as `okf-setup`) | New tables in `okf_rfc_demo`: `publications` (keyed by `publication_id`; `source` ∈ `sync`, `seeded_pre_phase_a`; owns no `context_ref` column), `deployments`, `deployment_heads`, `deployment_heads_history`, `concept_versions`, `snapshot_membership`, `relationship_assertions`, `context_ref_bindings` (append-only; unique on `context_ref`; Phase A on), `catalog_ownership`, `legacy_context_ref_bindings` (`context_ref`, `publication_id`, `origin`; may repeat a handle), `demo_evidence` (`source`, `context_ref`, `publication_id`, `note`). One view: `context_ref_resolution` = `context_ref_bindings` ∪ `legacy_context_ref_bindings` with a `binding_source` column. DDL and the view are in `sql/attribution_two_key.sql`. Never touch `agent_events`. |
| Seed pre-Phase-A rows (as `okf-setup`) | `publications`: `a25e1c0c…`, `674153c5…`, `53bd1651…` with `source = seeded_pre_phase_a`. `legacy_context_ref_bindings`: `okf:env-demo#a25e1c0ccbca → a25e1c0c…`, `okf:env-observe#674153c572f6 → 674153c5…`, `okf:env-observe#674153c572f6 → 53bd1651…` (never into `context_ref_bindings`, so uniqueness holds from Phase A on). `demo_evidence`: one row for the adapter tape (`53bd1651…`, source `adapter_tape_pr474_476d37dc`) and one for the legacy Catalog description (`a25e1c0c…`, source `legacy_catalog_description`). |
| Catalog prerequisites (as `okf-setup`) | Run the sample `setup.ts` to register shipped `okf-bundle` + `okf` in the project (today only the older `okf-concept` type exists). Create the profile-owned `okf-context-runtime` AspectType (`publication_id`, `published_snapshot_id`, `managed_by_deployment`, `managed_by_sync_id`). Push the derived bundle with the sample `push.ts` (as the sync-writer, which holds `catalogEditor` on the group) so the syncer has shipped-type entries to stamp. Leave `okf-derived-germany` (type `okf-concept`, no aspects) in place, labelled prior. |
| Beat 3 recording (as `okf-runtime-reader`) | After the push: `gcloud dataplex entries lookup <metric entry> --view=ALL` showing the 13-field `okf` aspect and, after the first sync, the `okf-context-runtime` pin; `curl …:lookupContext` on the same entry showing the YAML `context` without those fields; one call with 11 resources to show the ten-resource limit; the legacy entry lookup, labelled prior. |
| `context_ref` rule | Minted at commit, bound to one `publication_id`, never rebound. A rerun with a new observation mints a new handle. Resolution goes through the `context_ref_resolution` view; a legacy handle is ambiguous there and is only attributed when the event also carries the `publication_id`. |
| Identities | Reuse `PROFILE.md` hashing exactly as `derived_vectors.py` / `vectors_gen.py` do. Do not invent hashes; assert the CLI reproduces `53bd1651…` for the bundle on record before committing anything. |
| Gate | Second run prints `no-op` and writes nothing. Kill the process between `BQ_COMMITTED` and stamp; rerun completes stamp without a new publication. Removing one concept file removes only the ledger-owned entry. `deployment_heads_history` shows two rows after a deliberate republish of an unchanged snapshot. The five negative permission checks in `spec.md` §1.3 return `PERMISSION_DENIED` on tape. |
| Out | Attester. Scheduler (show the Cloud Run Job YAML naming the sync-writer only). `sync --from-catalog` (future). Sub-concept policy enforcement. |

## Phase B — BigQuery serve path against real tables (as `okf-runtime-reader`)

| Item | Detail |
|---|---|
| Retrieve | `okf_retrieve_context` reads `deployment_heads` → `snapshot_membership` → `concept_versions` with `mode: current` excluding superseded. Result shape unchanged from the trace on record (six items, one exclusion, `context_ref`). |
| Historical selection | `okf_retrieve_context` with `mode: historical` and an `as_of` date resolves the publication via `deployment_heads_history` and retrieves against it. This answers "which publication was current at T". It does not produce numbers. |
| Pin-or-fail-stale | A `context_ref` bound to a non-head publication returns `FAIL_STALE`; junk returns `FAIL_CLOSED`. Both are exercised in the tape. |
| Attested computation | Still `UNVERIFIABLE`, reason `no-execution`. The declared `parameter_schema` is returned and shown. Do not run SQL under the demo identity and call it attested. Numerical comparison and roll-up remain future executor/attester work, labelled `RFC text only`. |
| Attribution query | `sql/attribution_two_key.sql`. Events (`TOOL_COMPLETED`) are matched against `context_ref_resolution` on **both** `JSON_VALUE(content,'$.result.context_ref')` and the event-carried publication id (`$.result.publication_id` or `$.result.okf.publication_id`); `publications` is then joined by `publication_id` only. Band `attributed`: retrieve/lookup rows (14 today). Band `receipt_only`: the 13 `okf_run_attested_computation` rows whose event publication is NULL, kept and attributed by handle only, never merged. A second `SELECT` over `demo_evidence` lists the adapter-tape and legacy-Catalog rows. v0 (events only, runnable today) stays in `sql/sessions_by_context_ref.sql`. |
| Transcript for beat 5 | Replay the existing observe-agent session `f21ee192` rows (it is the observe agent, not a consume agent). No new agent run; do not pad `agent_events`. |
| Gate | Never-emit scan over every tool result: 0 hits. Queries are checked in with their results as JSON snapshots and the `bq` job id. Attribution query: band `attributed` sums to 14, band `receipt_only` sums to 13, no event row appears twice despite the legacy double-bound handle. |

## Phase C — `/rfc/full-demo/` page

| Item | Detail |
|---|---|
| Shape | Static viewer, vanilla JS, RFC tokens, six-beat stepper, deep links `#beat=1…6`. Same honesty chrome as `/rfc/demo/` (browser never calls GCP; identities pinned from CLI). |
| Beat 3 | Three panes: `entries.get --view=ALL` with the real `okf` aspect and stamped pin; `lookupContext` output without them plus the ten-resource / single-location / no-link-following notes; the `04fa3d56` transcript with its system prompt and the sentence "You can trust the number because it is verified" highlighted. Caption: "discovery works and can show a pin; it cannot carry a verdict, compare the pin to a head, or follow links." Legacy `okf-derived-germany` collapsed, labelled prior. |
| Beat 4 | The Phase A asciinema tape, with `BQ_COMMITTED`, `CATALOG_STAMPED`, each positive-check `OK`, and each of the five `PERMISSION_DENIED` calls as named marks. |
| Beat 5 | The history-selection query, the `parameter_schema`, the `UNVERIFIABLE` receipt, `FAIL_STALE`, `FAIL_CLOSED`; a visible "numbers: future executor/attester, RFC text only" label. |
| Beat 6 | Two tables from `sql/attribution_two_key.sql`: event-sourced attribution with the `attributed` and `receipt_only` bands, and `demo_evidence`, each with a source column. |
| Capability matrix | Rendered from `spec.md` §2 with the "Shown on" column; `RFC text only` rows carry that label visibly. |
| Checker | `rfc/full-demo/tools/check_full_demo.py`: beats present, session ids and publication prefixes match the checked-in snapshots, `ATTESTED` appears only inside the labelled non-normative shape, never-emit list absent from all tool JSON, `okf-derived-germany` labelled prior, every `RFC text only` row labelled, both system prompts present on beat 3. |
| RFC wiring | One clause added to the existing Prototype callout on `rfc/index.html` linking `./full-demo/`. No restyle. |
| Gate | Checker exits 0; `node --check` on the page JS; manual six-beat click-through with no console errors. |

## Phase D — recording (after Codex + Kimi dual LGTM on the Phase C PR)

- One asciinema cast of beats 3 → 6 (`entries.get` / `lookupContext`, `okf-context sync` twice,
  the negative checks, the serve queries, the attribution query), rendered to gif and a ~90 s H.264
  mp4 with the attribution tables as the poster frame.
- Keep `okf-bqaa-cli.mp4` as the Observe → Publish → Next-agent tape; do not re-record it.
- Push with `-c http.postBuffer=524288000` and verify `git ls-remote` before `gh pr create`.

## What stays CLI, what needs real GCP, what is stubbed or future

| Concern | Answer |
|---|---|
| Stays CLI | `kcmd push` (Catalog), `run.py` (adapter), `okf-context sync` (bridge), `bq query` (serve and attribution). |
| Needs real GCP | Service accounts and resource-specific IAM bindings (type-level, EntryGroup-level, table-level); BigQuery DDL/DML for the runtime, legacy-binding, evidence tables and the resolution view; Catalog aspect-type creation and entry stamping; sample `setup.ts` + `push.ts` for shipped types. All in `test-project-0728-467323`, `us-central1`, dataset `okf_rfc_demo`. |
| Stubbed in demo | Attester and `ATTESTED` verdict; scheduler. |
| Future / `RFC text only` | `sync --from-catalog`; numerical execution (comparison, roll-up); caller-delegated policy authorization, `policy_context_commitment`, mixed-policy fail-closed; permission-filtered empty LookupContext response. |
| Never | Re-run the observe agent; pad `agent_events`; rewrite the authored Cymbal fixture; change OKF v0.2 core, `PROFILE.md`, or SDK PR 474; start #435; claim a Dataplex built-in or roadmap item. |

## Order and rough sizing

1. Phase A (largest; identities, shipped types, seeds, the syncer). Own PR in the toolbox repo; link from here.
2. Phase B queries and snapshots. Small; can start once Phase A tables exist.
3. Phase C page. One PR here. Reviewers: Codex + Kimi.
4. Phase D recording. Follow-up after dual LGTM.

## Risks

| Risk | Mitigation |
|---|---|
| `kcmd` library import is not usable for aspect patching | Fall back to `gcloud dataplex entries update --aspects` from the CLI; note it in the PR. |
| Shipped `okf` AspectType cannot be registered beside the older `okf-concept` type in this project | They are independent types; keep both, label `okf-concept` prior. If Dataplex rejects, use a fresh EntryGroup `okf-rfc-demo-v2` and rebind the identities to it. |
| Legacy handle `okf:env-observe#674153c572f6` bound to two publications | Kept out of `context_ref_bindings`; resolved only with the event-carried `publication_id`; new handles are immutable. |
| EntryGroup-, type- or table-level bindings are rejected for a role above | Verify with the positive and negative checks before recording; if a level is unsupported, fall back to a dedicated project for the deployment or document the wider grant honestly. |
| Reviewer reads beat 3 as "Catalog is bad" | Beat 3 caption and the matrix's honest-limits line say Catalog's discovery projection is shipped and complete; the runtime sits on it. |
