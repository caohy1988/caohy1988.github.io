# Spec — full-version demo: sync architecture, KC vs BQ capability matrix, beats, success criteria

Slice of `intent.md`. Normative. Evidence cited here was read live on 2026-09-03 from
`test-project-0728-467323` (`bq query`, `gcloud dataplex`). See `CUSTOMER_STORIES.md` for the
transcripts and `ARCHITECTURE.md` for the diagram. Revised after Codex review of PR 15 (eight P1s):
v1 is source-bundle-authoritative, the bridge has an IAM contract, beat 3 tests shipped
OKF-in-Catalog, and everything Phase A/B does not implement is marked `RFC text only`.

## 1. Decision: is sync built into the services or an external command line?

**Answer to Haiyuan's Q1, one sentence.** Sync is an external CLI in v1, not a Dataplex or
BigQuery built-in; its direction is **authored/derived bundle → BigQuery commit → Catalog stamp**,
and a Catalog → BigQuery import is **not v1** (future, lossy, stubbed).

Knowledge Catalog stays the distribution and discovery projection that `kcmd push` already writes.
BigQuery stays the serving authority. The bridge is `okf-context sync`, a CLI subcommand of the
RFC's planned `toolbox/okf-context` package, run by a person in the demo and by a Cloud Run Job or
CI step in production. Hybrid (option C) describes the authority split; "external CLI" describes
the mechanism. Nothing inside Dataplex or BigQuery performs this step today, and the demo says so.

| Question | Decision | Why |
|---|---|---|
| Built-in or external? | **External CLI / job** | BigQuery has no reader for Catalog entries or custom aspects (INFORMATION_SCHEMA exposes none). Dataplex has no "materialize EntryGroup into a dataset" action. No cross-service transaction exists (RFC "Explicit states instead of pretended atomicity"). The hashing rules (`observation_id`, `snapshot_id`, `publication_id`) belong to the profile, not to either service. |
| Which of A / B / C? | **C, hybrid** | A alone under-describes the target (a managed path is plausible later). B alone is theatre. C names the authority split honestly and gives a path to managed without changing agent-facing contracts. |
| Source of truth for v1 sync | **The bundle on disk** (authored, or derived by the PR 474 adapter). Catalog is an output of sync, never its input, in v1. | The syncer must hash bundle bytes for `source_manifest_hash`. Catalog holds `overview` bodies and the `okf` aspect, but links stay prose and `extra` round-trips into frontmatter, so a Catalog-only read cannot reproduce authored identity. |
| Catalog → BigQuery import | **Not v1.** Future `sync --from-catalog`, labelled lossy (`derived-from-catalog`), stubbed in the demo. | Customers with bundles only in Catalog need it eventually; shipping it now would give two answers to Q1. |
| Trigger | Manual in demo; Cloud Run Job on Cloud Scheduler, or a CI job after `kcmd push`, in production | No push-completion event was verified; polling the EntryGroup `updateTime` is the documented fallback. |
| Unit of sync | One deployment = one bundle root + one EntryGroup + one set of runtime tables in one dataset | Matches the post's "one EntryGroup per bundle-owning team" and the RFC's one security domain per deployment. The table set, EntryGroup and type resources are the IAM boundary (§1.3). |
| Idempotency | `no-op` is defined on `deployment_heads`, not on row existence: if the head for the deployment already equals the computed `publication_id`, nothing is written. `publications` is written by `MERGE` on `publication_id`; a pre-seeded row (`source = seeded_pre_phase_a`, e.g. `53bd1651…`) is matched, its `source` becomes `sync` and `seeded_at` is preserved, and the head still advances because no head existed. New observation of an unchanged snapshot → new publication row (provenance, not silent). | RFC §06 republish semantics. `kcmd push` rewrites every entry every time; the syncer must not inherit that. |
| Ownership | BigQuery ledger keyed by deterministic deployment-scoped entry ids; `managed_by_*` stamps on `okf-context-runtime` | Generic `kcmd push` never deletes; delete-as-absence has to be carried by the syncer. The ledger is a convention; the authorization boundary is §1.3. |
| `context_ref` binding | **Immutable and non-rebindable** from Phase A on: one `context_ref` → exactly one `publication_id`, forever. A new publication mints a new `context_ref`. | Today one handle (`okf:env-observe#674153c572f6`) is bound to two publications; that is legacy evidence, not the contract. See beat 6. |
| Relationship to today's tools | `kcmd` / `push.ts`: Catalog write, unchanged. SDK `examples/okf_bqaa_adapter/run.py`: trace → derived bundle, unchanged (PR 474 merged). `okf-context sync`: new. The demo chains them. | No rewrite of shipped code. |

### 1.1 The sync algorithm (normative for Phase A of `plan.md`)

```
okf-context sync --bundle <root> --deployment <key> --entry-group <eg> [--project --location --dataset]
  runs as the deployment-scoped sync-writer identity (§1.3)
  1. validate     bundle parses; zero new OKF keys required
  2. observe      source_manifest_hash over every regular file → observation_id
  3. snapshot     compile concepts, versions, edges, membership → snapshot_id (domain-separated)
  4. plan         diff against deployment_heads; print adds / changes / removals (absence = delete)
  5. commit       stage rows under sync_id → MERGE publications ON publication_id (seeded row matched, not duplicated)
                  → BQ_COMMITTED → advance deployment_heads, append deployment_heads_history,
                  mint context_ref → publication_id binding (append-only, never rebound)
  6. stamp        for each owned Catalog entry: upsert okf-context-runtime {publication_id, published_snapshot_id, managed_by_*}
                  → CATALOG_STAMPED; unowned entries untouched; removed concepts: delete only ledger-owned entries
  7. status       print lag (publications committed vs stamped), entry counts, receipt UNVERIFIABLE until an attester runs
```

Exit non-zero and leave `deployment_heads` untouched if step 5 fails. If step 6 fails after 5, status
reports `BQ_COMMITTED, CATALOG_PENDING`; a rerun of `sync` completes the stamp without a new publication.

### 1.2 What is real, recorded, stubbed, and future in the full demo

The second column is the v1 target this spec sets. The third column is what `/rfc/full-demo/`
(PR 16) actually captured on 2026-09-03; it was added after Codex review so that no deferred item
reads as executed. Everything in the third column marked **Not done** or **Not built** is shown on
the page as `RFC text only`, and `tools/check_full_demo.py` asserts those labels.

| Piece | v1 target | Status on 2026-09-03 (PR 16) |
|---|---|---|
| BQAA trace in `okf_rfc_demo.agent_events` | Real. 212 rows, 4 sessions. Not re-run. | **Captured.** Live per-session count (4 sessions, 212 rows); three sessions pulled (209 rows); `a63c3e86…` (3 rows, no tool call) counted, not pulled. |
| Adapter trace → derived bundle | Real, SDK `main` after PR 474. Reproduced against `476d37dc`. | **Captured.** SDK `main` `4f54b5c` reproduced `53bd1651…` before the push. |
| Shipped `okf-bundle` entries + `okf` aspect | Real, after running the sample `setup.ts` + `push.ts` in Phase A. | **Captured**, run by the operator (not `okf-setup` / sync-writer): AspectType `okf`, EntryType `okf-bundle`, 8 entries; `entries.get` vs `lookupContext` on record. |
| `okf-context sync` commit into BigQuery runtime tables | Real BigQuery DDL/DML into `okf_rfc_demo` (new tables). Built in Phase A. | **Not built.** Only the DDL + seeds ran (as the operator). `deployment_heads`, history and `context_ref_bindings` are empty. No `BQ_COMMITTED`, no `no-op`. `RFC text only` on beat 4. |
| Catalog stamp on `okf-context-runtime` | Real Catalog write, aspect type to be created by the setup identity in Phase A. | **Not done.** No `okf-context-runtime` AspectType, no pin, no `CATALOG_STAMPED`. `RFC text only` on beats 3 and 4. |
| IAM bootstrap, identities, positive and negative checks, setup retirement (§1.3) | Real; to be recorded in the Phase A tape. | **Not done.** No service account, custom role, table-level grant, boundary probe or `PERMISSION_DENIED` check exists yet; every job ran as the operator (`bq_jobs_identity.json`). `RFC text only` on beat 4. |
| Pin-or-fail-stale (`FAIL_STALE`) | Real query against `deployment_heads`. | **Partly.** `FAIL_CLOSED`, `NO_HEAD`, `AMBIGUOUS_LEGACY` are live query results; `FAIL_STALE` needs a head and none exists. `RFC text only` on beat 5. |
| Scheduler / Cloud Run Job | Stubbed: job YAML shown, CLI run by hand. | Not shown; `RFC text only`. |
| Attester / `ATTESTED` verdict | Stubbed: verdict `UNVERIFIABLE`, reason `no-execution`. Nothing on the page says `ATTESTED`. | As specified: every receipt `UNVERIFIABLE`; beat 5 labels the pane live trace + stubbed attester. |
| Numerical execution (quarter comparison, roll-up) | Future executor/attester work. `RFC text only`. | `RFC text only`. |
| Caller-delegated policy authorization, `policy_context_commitment`, mixed-policy fail-closed | `RFC text only`. Not implemented in Phase A/B. | `RFC text only`. |
| `sync --from-catalog` | Future. `RFC text only`. | `RFC text only`. |
| Page | Viewer of recorded runs, same as today. Browser never calls GCP. | As specified. |

### 1.3 IAM contract for the bridge (normative, resource-specific, bootstrappable)

**Scope.** This section is the Phase A contract, written as requirements. Nothing in §1.3 has been executed on PR 16: no
service account, custom role, table-level grant, boundary EntryGroup, positive check or negative check exists, and no tape
has been recorded. Every capture behind `/rfc/full-demo/` ran as the operator (`live/bq_jobs_identity.json`). Where a
sentence below says what the tape "must" show, that is the acceptance criterion for Phase A, labelled `RFC text only`
on the page until it is met.

Four principals in `test-project-0728-467323`: one human **bootstrap operator** and three service
accounts. Every grant below names the resource it is bound to; nothing is granted at a wider scope
than the row says. Role and permission facts are from the Dataplex IAM roles page
(`docs.cloud.google.com/dataplex/docs/iam-roles`): EntryGroup, EntryType and AspectType **creation**
permissions are checked on the **project**; `dataplex.entryTypes.use` and `dataplex.aspectTypes.use`
are granted on the **type resource**; `searchEntries` needs `dataplex.projects.search` on the
**project**; `setIamPolicy` on EntryGroups and EntryTypes is in `roles/dataplex.catalogAdmin`, and on
AspectTypes in `roles/dataplex.aspectTypeOwner`. BigQuery grants use table-level IAM
(`bq add-iam-policy-binding … project:dataset.table`) so the sync writer never touches `agent_events`.

**Who must install the boundary.** Service accounts cannot grant themselves anything, and
`roles/iam.serviceAccountAdmin` cannot create custom roles, edit project IAM, or set Dataplex IAM.
So every binding call must be made by the **bootstrap operator**: the human project Owner account that
already runs `gcloud` in this project. In Phase A that account will hold, for the duration of setup only, the exact
policy-owner roles below, and each binding command must be recorded on tape under that identity. After
setup the operator must keep only what the demo needs at run time (impersonation of the sync writer and
the reader). None of these bindings exists yet (PR 16 status: not done).

| Principal | Resource | Grant | Why | Lifetime |
|---|---|---|---|---|
| bootstrap operator (human Owner) | project | `roles/iam.roleAdmin` | create custom role `okfCatalogSearch` | setup only; to be revoked |
| | project | `roles/resourcemanager.projectIamAdmin` | bind project-level roles to the three SAs | setup only; to be revoked |
| | project | `roles/iam.serviceAccountAdmin` | create the three SAs; bind `serviceAccountTokenCreator` on each SA resource | setup only; to be revoked |
| | project | `roles/dataplex.catalogAdmin` | `entryGroups.setIamPolicy`, `entryTypes.setIamPolicy` on `okf-rfc-demo`, `okf-rfc-demo-boundary`, `okf-bundle` | setup only; to be revoked |
| | project | `roles/dataplex.aspectTypeOwner` | `aspectTypes.setIamPolicy` on `okf`, `okf-context-runtime` | setup only; to be revoked |
| | dataset `okf_rfc_demo` | `roles/bigquery.dataOwner` | `bigquery.tables.setIamPolicy` for the nine table-level bindings | setup only; to be revoked |
| | SA `okf-sync-writer-okf-rfc-demo`, SA `okf-runtime-reader` | `roles/iam.serviceAccountTokenCreator` on each SA | run the demo by impersonation | kept |
| | SA `okf-setup` | `roles/iam.serviceAccountTokenCreator` | run setup by impersonation | setup only; to be revoked (check 7) |
| `okf-setup` (one-time) | project | `roles/dataplex.catalogEditor` (`entryGroups.create`, `entryTypes.create`) and `roles/dataplex.aspectTypeOwner` (`aspectTypes.create`) | type and group creation is checked on the project, not on the group | setup only; to be revoked (check 6) |
| | dataset `okf_rfc_demo` | `roles/bigquery.dataOwner` | table DDL, the `context_ref_resolution` view, seed `MERGE`s (`sql/setup_runtime_tables.sql`) | setup only; to be revoked |
| | project | `roles/bigquery.jobUser` | run the DDL jobs | setup only; to be revoked |
| `okf-sync-writer-okf-rfc-demo` | EntryGroup `okf-rfc-demo` | `roles/dataplex.catalogEditor` | `entries.create/patch/delete` inside this group only | kept |
| | EntryType `okf-bundle` | `roles/dataplex.entryTypeUser` | create entries of that type (the identity the sample `push.ts` uses) | kept |
| | AspectType `okf`, AspectType `okf-context-runtime` | `roles/dataplex.aspectTypeUser` on each | attach the shipped aspect; stamp the profile aspect | kept |
| | tables `publications`, `deployments`, `deployment_heads`, `deployment_heads_history`, `concept_versions`, `snapshot_membership`, `relationship_assertions`, `context_ref_bindings`, `catalog_ownership` | `roles/bigquery.dataEditor` **per table** | no dataset grant, so `agent_events`, `legacy_context_ref_bindings`, and `demo_evidence` are unreachable | kept |
| | project | `roles/bigquery.jobUser` | run the commit jobs | kept |
| `okf-runtime-reader` | EntryGroup `okf-rfc-demo` | `roles/dataplex.catalogViewer` | `entries.get` and `lookupContext` on entries in this group | kept |
| | project | custom role `okfCatalogSearch` = {`dataplex.projects.search`} | `searchEntries` is project-scoped; the custom role limits the project grant to one permission | kept |
| | dataset `okf_rfc_demo` | `roles/bigquery.dataViewer` | `SELECT` over runtime tables, the view, legacy bindings, `demo_evidence`, `agent_events` | kept |
| | project | `roles/bigquery.jobUser` | run the serve and attribution queries (SELECT only; `sql/attribution_two_key.sql`) | kept |

**Credential acquisition.** The human operator must impersonate each service account through an
**isolated gcloud configuration** (`gcloud config configurations create <name> --no-activate`,
`CLOUDSDK_ACTIVE_CONFIG_NAME=<name>`, `gcloud config set auth/impersonate_service_account <sa>`), one
configuration per SA, never the default configuration. `bq` reads that setting; it has no
flag of its own (bq 2.1.28 rejects `--impersonate_service_account`, as the operator
verified on 2026-09-03; with the gcloud setting bq reports "All API calls will be executed as [<sa>]").
`gcloud` commands may also pass `--impersonate-service-account` explicitly. Every SQL statement is
piped over stdin, never passed as a positional argument. Impersonation requires
`roles/iam.serviceAccountTokenCreator` **on each service account resource** for the operator,
one binding per SA. The Phase A tape must show the active configuration name before each step and, after each
BigQuery step, the `user_email` that `INFORMATION_SCHEMA.JOBS` reports for the acting service account (Phase A, not yet run), so that the identity
will be demonstrated rather than asserted; today the only `user_email` on record is the operator's. The Cloud
Run Job will run as the sync writer directly (no impersonation). No identity is to be granted to the job other
than the sync writer.

**Setup order for the Phase A tape** (each command to be recorded under its own acting identity, not yet run):

1. Operator: create SAs; create `okfCatalogSearch`; bind setup roles; bind Token Creator on `okf-setup`.
2. `okf-setup` (isolated configuration `okf-setup`): sample `setup.ts` (shipped `okf-bundle`, `okf`); `aspect-types create okf-context-runtime`; create EntryGroup `okf-rfc-demo-boundary` and one disposable entry `boundary-probe` of type `okf-bundle` in it; `sql/setup_runtime_tables.sql` piped to `bq query` (tables, view, seed `MERGE`s).
3. Operator (default configuration): bind sync-writer and reader roles on the now-existing type, group, and table resources; bind Token Creator on the two run-time SAs.
4. Positive checks 1–3 and negative checks 1–5.
5. Operator: revoke every `okf-setup` role and the dataset `dataOwner`; run check 6; revoke Token Creator on `okf-setup`; run check 7; delete EntryGroup `okf-rfc-demo-boundary`; revoke the operator's own setup-only roles.

**Positive checks** (Phase A, not yet run; each allowed operation to be exercised on tape exactly once, expected `OK`):

1. `okf-setup`: `aspect-types create okf-context-runtime`; `entries patch` on `okf-rfc-demo-boundary/entries/boundary-probe` (expected `OK`, so that negative check 2 below can fail only on IAM); `sql/setup_runtime_tables.sql` piped to `bq query` under configuration `okf-setup`.
2. `okf-sync-writer-okf-rfc-demo`: `entries create` of type `okf-bundle` with the `okf` aspect in `okf-rfc-demo`; `entries patch` adding `okf-context-runtime`; `MERGE` into `publications`, `INSERT` into `deployment_heads`; `entries delete` of a ledger-owned entry.
3. `okf-runtime-reader`: `entries get --view=ALL`; `lookupContext` on one entry; `searchEntries` with `aspect:…okf.okf_type=metric`; the two marked `SELECT`s in `sql/attribution_two_key.sql`, each piped to `bq query` as its own invocation under configuration `okf-reader`.

**Negative checks** (Phase A, not yet run: seven checks, nine real API calls, each call expected `PERMISSION_DENIED`,
to be recorded on tape and asserted by the checker; check 6 is three calls):

1. `okf-sync-writer-okf-rfc-demo`: `SELECT COUNT(*) FROM agent_events` → expected `PERMISSION_DENIED` (no dataset grant, no table grant).
2. `okf-sync-writer-okf-rfc-demo`: the **same** `entries patch` on `okf-rfc-demo-boundary/entries/boundary-probe` that `okf-setup` will have just completed successfully → expected `PERMISSION_DENIED`. Custom group, existing user-created entry, identical request body; the only variable is the missing cross-group grant.
3. `okf-sync-writer-okf-rfc-demo`: `aspect-types create okf-context-runtime-2` → expected `PERMISSION_DENIED` (no project-level type creation).
4. `okf-runtime-reader`: `entries patch` on an entry that carries the runtime pin → expected `PERMISSION_DENIED`.
5. `okf-runtime-reader`: `INSERT INTO deployment_heads` → expected `PERMISSION_DENIED`.
6. Post-cleanup, `okf-setup` (still impersonable after step 5 removes its roles), three calls: (6a) `aspect-types update okf --description=x`, (6b) `aspect-types delete okf-context-runtime`, (6c) `aspect-types set-iam-policy okf` → each expected `PERMISSION_DENIED`, which would show the project-wide AspectType authority is gone.
7. Post-cleanup, operator (default configuration): `gcloud auth print-access-token --impersonate-service-account=okf-setup@…` → expected `PERMISSION_DENIED` on `generateAccessToken`, which would show a closed impersonation path; the `okf-setup` gcloud configuration is then to be deleted.

What this buys and what it does not: the table set, the EntryGroup, and the type resources are the
enforceable boundary. Inside one EntryGroup, `catalogEditor` can delete any entry, so the ownership
ledger remains a discipline, not an authorization control. If EntryGroup- or type-level bindings are
rejected by the API for any role above, the plan's risk table says to fall back to a dedicated
project and document the wider grant; no Dataplex built-in is assumed.

## 2. Capability matrix: what OKF-in-Catalog cannot do that the BigQuery deployment can

"KC-only" means the shipped path after `setup.ts` + `push.ts`: `okf-bundle` entries, the 13-field
`okf` aspect, `searchEntries`, `LookupContext`, `entries.get view=ALL`, EntryGroup IAM. The
"Shown on" column is the honesty flag: a beat number means the page shows it from a recorded run;
`RFC text only` means the page quotes the RFC and says so.

| # | Capability | KC-only | BigQuery deployment | Live evidence | Shown on |
|---|---|---|---|---|---|
| 1 | **Pin-or-fail-stale** | **Can display** the pin Phase A would stamp (`okf-context-runtime.publication_id`) and filter on it with a search predicate. **Cannot compare** it to `deployment_heads` or refuse a stale request; LookupContext does not render it at all. | `deployment_heads` is the comparison target; a request presenting a non-head `publication_id` returns `FAIL_STALE`. | After Phase A: stamped `okf-bundle` entries. Prior evidence, labelled legacy: `okf-derived-germany` (type `okf-concept`, no aspects) names `a25e1c0c…` only as prose in `entrySource.description` while `674153c5…` and `53bd1651…` also exist. | 3, 5 |
| 2 | **`deployment_heads` history** | One mutable state per entry, `createTime` / `updateTime` only. "Which publication was current for this deployment at time T" has no answer. | `deployment_heads_history (deployment_key, publication_id, snapshot_id, committed_at, sync_id)` answers **which publication** was current at T. It holds no revenue values; numerical prior-quarter comparison is future executor/attester work. | Session `f21ee192` question 4 ("How did Germany compare to the prior quarter?"): the tool returned the same six current items; the historical publication selection is unanswerable from Catalog. | 5 (selection); numbers `RFC text only` |
| 3 | **Attested execution and verdicts** | Displays `runtime`, `parameters`, `computation`, `executor`, `attester` and stops. No verdict field exists in the contract. | `run_attested_computation` returns `verdict` ∈ {ATTESTED, UNVERIFIABLE, REJECTED} with reason and `receipt_id`; demo verdict is always `UNVERIFIABLE`. | Session `04fa3d56` (no-verdict lookup, prompt allowed "sanctioned computation" language): "You can trust the number because it is verified." Session `f21ee192` (verdict field, prompt required "unproven" unless `ATTESTED`): "No. The number is unproven." Illustration, not a controlled comparison (see story 1). | 3, 5 |
| 4 | **SQL join of context and evidence** | Catalog is not queryable with SQL and cannot be joined to `agent_events`. | Events match the `context_ref_resolution` view (legacy ∪ Phase-A bindings) on **both** event-carried `context_ref` and event-carried `publication_id`, then join `publications` by `publication_id`; receipt-only rows (NULL publication) are banded separately; adapter-tape and Catalog observations are seeded `demo_evidence` rows, not event rows. | Real query today returns 5 (session, tool, context_ref, publication) groups; Catalog can display none of them. | 6 |
| 5 | **BQAA `context_ref` seam** | No place for an opaque runtime handle; `extra` round-trips into authored frontmatter via `pull.ts`. | `context_ref` on every tool result, never-emit list enforced, immutable binding to one publication. | 27 of 27 `TOOL_COMPLETED` rows carry `context_ref`; 0 carry `concept_version_id`, paths, principal, SQL. | 2 |
| 6 | **Sub-EntryGroup policy** | Enforcement unit is the EntryGroup; IAM cascades; `overview` exposes full bodies. Any `catalogViewer` on the group reads the Policy body. | RFC: one security domain per deployment, caller-delegated authorization, `policy_context_commitment`, mixed-policy fail-closed. **Not implemented in Phase A/B.** | Real: EntryGroup IAM structure and question 7's `governed_by` edge. | Catalog side 3; BigQuery side `RFC text only` |
| 7 | **Observation → Snapshot → Publication chain** | Identities are Dataplex timestamps. "Every push writes every Entry." Two agents cannot prove they read the same revision. | Three content identities plus immutable `publications` rows; identical republish is a no-op; unchanged-snapshot republish is a provenance event. | Adapter output on record: observation `85ea62a9…`, snapshot `f18befd0…`, publication `53bd1651…`; in-process pin `674153c5…`; Catalog pin `a25e1c0c…`. | 4 |
| 8 | **Delete-as-absence ledger vs `kcmd` no-delete** | Generic `kcmd push` creates or patches; `sync.ts` has "TODO: Handle creates and deletes". A superseded concept is served until someone deletes the entry or the whole EntryGroup. | Deletion is absence from the next snapshot; the ledger removes only owned entries. `current` mode excludes superseded concepts at query time. | `Customer revenue (legacy)`, out of force since 2026-06-20, excluded in 13 of 13 retrievals across `f21ee192` and `1e6dfed7`. | 4, 5 |
| 9 | **LookupContext limits** | Per Google's docs and the post: up to **ten resources per call**; **single location** in the endpoint; **does not follow links** out of a concept body (the agent must name referenced concepts); **does not render custom aspects** (the `okf` fields need `entries.get view=ALL`); **permission-filtered**, and an empty response if the caller has no permission on the requested resources. | Bounded SQL traversal and join over `snapshot_membership` and `relationship_assertions` returns the governed closure in one query with an explicit depth bound, and the Context Envelope carries `publication_id`, lifecycle mode, manifest and `envelope_id`. | After Phase A: LookupContext on the pushed `okf-bundle` entry returns the YAML `context` without the `okf` aspect; `entries.get view=ALL` returns it. Sources: KC blog 2026-08-26; `docs.cloud.google.com/dataplex/docs/retrieve-data-context`. | 3 (omission, 10-limit, no-link-following); permission-empty `RFC text only` |

Honest limits, to be printed on the page: the Catalog mapping itself (one entry per concept, `okf`
aspect, `overview` body, index and log entries, parent hierarchy) is shipped and complete; the RFC
adds pins and a ledger to it, not a rival projection. IAM on the EntryGroup, the type resources and
the runtime tables is the only boundary that is enforceable today; the ledger is a discipline.

## 3. Demo beats (`/rfc/full-demo/`, six beats, deep-linkable `#beat=1…6`)

The **Source** column is the target tape. **Captured on PR 16** says what the page shows today;
anything else in the row is quoted as `RFC text only` on the page.

| # | Beat | What the visitor sees | Source (target; page is static) | Must prove | Captured on PR 16 |
|---|---|---|---|---|---|
| 1 | **Ask** | The real question and the 12 follow-ups from session `f21ee192`. Two traps: the dead metric, and over-claiming trust. | `agent_events` `USER_MESSAGE_RECEIVED` rows | Nothing is fictional. | Yes: 12 questions from the pulled rows. |
| 2 | **Observe** | One SQL query and its result: event histogram (Σ 180), the 24 tool calls, the `context_ref` on every result, the never-emit scan (0 hits). | `bq query` transcript, checked in | BQAA is observer-only; telemetry is not the bundle. | Yes: histogram, 24 tool calls, never-emit scan over 27 payloads. |
| 3 | **Catalog path: where it stops** | Recorded **after** `setup.ts` + `push.ts`: (a) `entries.get --view=ALL` on the pushed `okf-bundle` metric entry showing the real 13-field `okf` aspect and, after Phase A, the `okf-context-runtime` pin it would then carry; (b) `lookupContext` on the same entry returning the YAML `context` with **no** `okf` fields and no pin, plus the ten-resource and no-link-following limits called out; (c) session `04fa3d56`'s transcript: "You can trust the number because it is verified", with its system prompt shown beside it. The legacy entry `okf-derived-germany` (type `okf-concept`, no aspects) appears collapsed, labelled "prior experiment, not shipped OKF-in-KC". | `gcloud` transcripts; `agent_events` session `04fa3d56` | Discovery works and can display a pin; it cannot carry a verdict, compare a pin to a head, or follow links. | Mostly: shipped aspect, `lookupContext` omission, ten-resource error, transcript, legacy entry. **Not** the `okf-context-runtime` pin (no sync). No-link-following not exercised. |
| 4 | **Sync (CLI)** | `okf-context sync` as the sync-writer identity: validate → observe → snapshot → plan (adds 8, removes 0) → `BQ_COMMITTED` → heads advanced → new `context_ref` minted → `CATALOG_STAMPED` → status. Second run: `no-op`. Then the positive checks, boundary checks 1–5, and post-cleanup checks 6–7 (nine `PERMISSION_DENIED` calls in all). | asciinema tape of the Phase A CLI | Sync is external, idempotent, explicit-state, least-privilege. | **No.** Syncer not built. The page prints `BQ_COMMITTED`, `CATALOG_STAMPED`, `no-op` and `PERMISSION_DENIED` only inside the quoted `RFC text only` algorithm and IAM contract; none is shown as an executed or live outcome. Page shows the algorithm and IAM contract as `RFC text only` plus the operator-run `setup.ts` / `push.ts` / DDL. |
| 5 | **Serve (BigQuery)** | Four SQL results: `deployment_heads` for the deployment; `deployment_heads_history` answering "which publication was current at T"; retrieve `current` returning the six items and the one exclusion, with the declared `parameter_schema` (`region`, `quarter_start`, `quarter_end`); `run_attested_computation` receipt `UNVERIFIABLE` with reason; a non-head `context_ref` → `FAIL_STALE`; junk → `FAIL_CLOSED`. Session `f21ee192` transcript beside it: "No. The number is unproven." Caption: numerical comparison and roll-up are future executor/attester work. | `bq query` transcripts; existing CLI tape | Pin, history selection, lifecycle, honest verdict, fail-stale, fail-closed. | Partly: heads and history queries run and return 0 rows; `FAIL_CLOSED` / `NO_HEAD` / `AMBIGUOUS_LEGACY` live; receipt and answers live. **Not** `FAIL_STALE` (needs a head). |
| 6 | **Attribution** | Two tables. (a) Event-sourced: `agent_events` matched on both event-carried `context_ref` and event-carried `publication_id` against the `context_ref_resolution` view, then joined to `publications` by `publication_id`; one row per (session, tool, context_ref, publication); the 13 receipt-only rows (NULL event publication) appear as a labelled band attributed by handle only. (b) Separately sourced: `demo_evidence` rows for the adapter tape's `53bd1651…` and the legacy Catalog description's `a25e1c0c…`, each with its source column. Caption: the legacy handle `okf:env-observe#674153c572f6` was bound to two publications before Phase A; refs minted by `sync` are immutable. SQL: the two `SELECT`s in `sql/attribution_two_key.sql`, run as `okf-runtime-reader` under an isolated gcloud configuration, each piped over stdin as its own invocation; DDL lives in the setup-owned `sql/setup_runtime_tables.sql`. | two `bq query` transcripts; `demo_evidence` seed table | The gap is a SQL result, not a slide, and no event is misattributed. | Yes, run as the operator (not yet `okf-runtime-reader`): 14 / 13, two evidence rows. |

Beats 1, 2, 5 reuse material already on `/rfc/demo/`. Beats 3, 4, 6 are new. The existing
`okf-bqaa-cli.mp4` stays as the Observe → Publish → Next-agent tape; a new ~90 s tape covers 3 → 6
after dual LGTM (see `plan.md`).

## 4. Success criteria

- (Met on PR 16 as text; the tape is Phase A.) A cold reader can state the sync answer in one sentence after beat 4: "an external CLI I run or
  schedule; bundle to BigQuery first, Catalog stamp second; Catalog-to-BigQuery import is not v1."
- Beat 3 shows shipped OKF-in-KC (`okf-bundle` + `okf` aspect via `entries.get view=ALL`) and
  LookupContext omitting it; the legacy `okf-concept` entry is labelled prior.
- Beat 3 quotes one real overclaim verbatim with its session id and its system prompt.
- Beat 6 is a real query result over `okf_rfc_demo` that a visitor could rerun with `bq query`:
  events matched on both handle and publication through one resolution view, `publications` joined
  by id only, receipt-only rows banded, non-event evidence in `demo_evidence`.
- Every capability row in §2 is either shown on a beat or marked `RFC text only` on the page.
- (Phase A; not yet met on PR 16.) The bootstrap operator must install every binding on tape; every positive check must return `OK`; all seven negative checks (nine API calls) must return `PERMISSION_DENIED`, including the two post-cleanup checks that would show a retired `okf-setup`; and the tape must show each BigQuery step's `user_email` matching the declared identity. Today every `user_email` on record is the operator's.
- Never-emit scan over every agent-facing payload on the page returns 0 hits.
- `python3 rfc/full-demo/tools/check_full_demo.py` (Phase C) exits 0: beats present, session ids and
  publication ids match the checked-in transcripts, no `ATTESTED` string outside the labelled Phase 4 shape,
  every `RFC text only` row carries that label in the rendered matrix.
- No change to OKF v0.2 core, `PROFILE.md` hashing, SDK PR 474, or the 180-row export.
