# Spec — full-version demo: sync architecture, KC vs BQ capability matrix, beats, success criteria

Slice of `intent.md`. Normative. Evidence cited here was read live on 2026-09-03 from
`test-project-0728-467323` (`bq query`, `gcloud dataplex`). See `CUSTOMER_STORIES.md` for the
transcripts and `ARCHITECTURE.md` for the diagram.

## 1. Decision: is sync built into the services or an external command line?

**External command line in v1, hybrid by design (option C).** Knowledge Catalog stays the
distribution and discovery projection that `kcmd push` already writes. BigQuery stays the serving
authority. The bridge between them is `okf-context sync`, a CLI subcommand of the RFC's planned
`toolbox/okf-context` package, run by a person in the demo and by a Cloud Run Job or CI step in
production. Nothing inside Dataplex or BigQuery performs this step today, and the demo must say so.

| Question | Decision | Why |
|---|---|---|
| Built-in or external? | **External CLI / job** | BigQuery has no reader for Catalog entries or custom aspects (INFORMATION_SCHEMA exposes none). Dataplex has no "materialize EntryGroup into a dataset" action. No cross-service transaction exists (RFC "Explicit states instead of pretended atomicity"). The hashing rules (`observation_id`, `snapshot_id`, `publication_id`) belong to the profile, not to either service. |
| Which of A / B / C? | **C, hybrid** | A alone under-describes the target (a managed path is plausible later). B alone is theatre. C names the authority split honestly and gives a path to managed without changing agent-facing contracts. |
| Direction | **Bundle → BigQuery (commit) → Catalog (stamp)**, with **Catalog → BigQuery import** as a labelled, lossy fallback | The syncer needs bundle bytes to hash `source_manifest_hash`. Catalog holds `overview` bodies and the `okf` aspect, but links stay prose and `extra` round-trips into frontmatter, so a Catalog-only read cannot reproduce authored identity. Customers with bundles only in Catalog get `sync --from-catalog`, which materializes entries into a bundle directory first and is labelled `derived-from-catalog`. |
| Trigger | Manual in demo; Cloud Run Job on Cloud Scheduler, or a CI job after `kcmd push`, in production | Catalog has no push-completion event the syncer can subscribe to that we verified; polling by `updateTime` on the EntryGroup is the documented fallback. |
| Unit of sync | One deployment = one bundle root + one EntryGroup + one BigQuery dataset | Matches the post's "one EntryGroup per bundle-owning team" and the RFC's one security domain per deployment. |
| Idempotency | Same observation → same `snapshot_id` → publication no-op; new observation of unchanged snapshot → new publication row (provenance, not silent) | RFC §06 republish semantics. `kcmd push` rewrites every entry every time; the syncer must not inherit that. |
| Ownership | BigQuery ledger keyed by deterministic deployment-scoped entry ids; `managed_by_*` stamps on `okf-context-runtime` | Generic `kcmd push` never deletes; delete-as-absence has to be carried by the syncer. |
| Relationship to today's tools | `kcmd` / `push.ts`: Catalog write, unchanged. SDK `examples/okf_bqaa_adapter/run.py`: trace → derived bundle, unchanged (PR 474 merged). `okf-context sync`: new. The demo chains them. | No rewrite of shipped code. |

### 1.1 The sync algorithm (normative for Phase A of `plan.md`)

```
okf-context sync --bundle <root> --deployment <key> --entry-group <eg> [--project --location --dataset]
  1. validate     bundle parses; zero new OKF keys required
  2. observe      source_manifest_hash over every regular file → observation_id
  3. snapshot     compile concepts, versions, edges, membership → snapshot_id (domain-separated)
  4. plan         diff against deployment_heads; print adds / changes / removals (absence = delete)
  5. commit       stage rows under sync_id → BQ_COMMITTED → advance deployment_heads, append deployment_heads_history
  6. stamp        for each owned Catalog entry: upsert okf-context-runtime {publication_id, published_snapshot_id, managed_by_*}
                  → CATALOG_STAMPED; unowned entries untouched; removed concepts: delete only ledger-owned entries
  7. status       print lag (publications shown vs served), entry counts, receipt UNVERIFIABLE until an attester runs
```

Exit non-zero and leave `deployment_heads` untouched if step 5 fails. If step 6 fails after 5, status
reports `BQ_COMMITTED, CATALOG_PENDING`; a rerun of `sync` completes the stamp without a new publication.

### 1.2 What is real, recorded, and stubbed in the full demo

| Piece | v1 demo status |
|---|---|
| BQAA trace in `okf_rfc_demo.agent_events` | Real. 212 rows, 4 sessions. Not re-run. |
| Adapter trace → derived bundle | Real, SDK `main` after PR 474. Reproduced against `476d37dc`. |
| `okf-context sync` commit into BigQuery runtime tables | Real BigQuery DDL/DML into `okf_rfc_demo` (new tables). Built in Phase A. |
| Catalog stamp on `okf-context-runtime` | Real Catalog write, needs the aspect type created first (it does not exist in the project today). |
| Shipped `okf-bundle` entries | Must be created by running the sample `setup.ts` + `push.ts`. Today the project has only the RFC's older `okf-concept` type and one entry. |
| Scheduler / Cloud Run Job | Stubbed: we show the job YAML and run the CLI by hand. |
| Attester | Stubbed: verdict `UNVERIFIABLE`, reason `no-execution`. Nothing on the page says `ATTESTED`. |
| Page | Viewer of recorded runs, same as today. Browser never calls GCP. |

## 2. Capability matrix: what OKF-in-Catalog cannot do that the BigQuery deployment can

"KC-only" means the shipped path: `kcmd push`, `okf` aspect, `searchEntries`, `LookupContext`,
`entries.get`, EntryGroup IAM. Evidence column cites what we can show on screen today.

| # | Capability | KC-only | BigQuery deployment | Live evidence we can show |
|---|---|---|---|---|
| 1 | **Pin-or-fail-stale** | Cannot enforce. A search predicate on `publication_id` filters entries; it cannot compare to a head or refuse. LookupContext carries no pin at all. | `deployment_heads` is the comparison target; a request presenting a stale `publication_id` fails stale instead of silently jumping to latest. | Catalog entry `okf-derived-germany` carries `a25e1c0c…` only as prose in `entrySource.description`. Two later publications (`674153c5…`, `53bd1651…`) exist and Catalog cannot tell which is current. |
| 2 | **`deployment_heads` history** | One mutable state per entry, `createTime` / `updateTime` only. "What was current for this deployment last quarter" has no answer. | `deployment_heads_history (deployment_key, publication_id, snapshot_id, committed_at, sync_id)` answers it in one query. | Session `f21ee192` question 4: "How did Germany compare to the prior quarter?" The tool returned the same six current items; the prior-quarter context is unanswerable from Catalog. |
| 3 | **Attested execution and verdicts** | Displays `runtime`, `parameters`, `computation`, `executor`, `attester` and stops. Nothing runs, nothing issues a verdict. | `run_attested_computation` returns `verdict` ∈ {ATTESTED, UNVERIFIABLE, REJECTED} with a reason and `receipt_id`; the agent must carry it. | Session `04fa3d56` (Catalog-shaped lookup, no verdict field): agent answered "You can trust the number because it is verified." Session `f21ee192` (verdict field present): agent answered "No. The number is unproven." 12 of 12 times. |
| 4 | **SQL join of context and evidence** | Catalog is not queryable with SQL and cannot be joined to `agent_events`. | `JOIN agent_events ON JSON_VALUE(content,'$.result.context_ref')` to `publications` and `deployment_heads_history` answers "which sessions used which publication" and "which sessions used a stale one". | Real query in beat 6 returns 3 distinct (session, context_ref) rows from 5 tool-result groups; Catalog can display none of them. |
| 5 | **BQAA `context_ref` seam** | No place to put an opaque runtime handle; `extra` round-trips into authored frontmatter via `pull.ts`. | `context_ref` on every tool result, never-emit list enforced; the mapping table binds `context_ref` → `publication_id`. | 27 of 27 `TOOL_COMPLETED` rows carry `context_ref`; 0 carry `concept_version_id`, paths, principal, SQL. |
| 6 | **Sub-EntryGroup policy** | Enforcement unit is the EntryGroup; `overview` exposes full bodies; IAM cascades. A Policy concept in the same group as tables is readable by every `catalogViewer` on the group. | One security domain per deployment, caller-delegated BigQuery authorization, `policy_context_commitment` inside the Context Envelope. Mixed-policy bundles fail closed at projection time. | Question 7 in `f21ee192`: "What policy governs active-customer revenue recognition?" returns `Revenue recognition eligibility (Policy)` via `governed_by`; in Catalog that policy body is one `entries.get` away for anyone on the group. |
| 7 | **Observation → Snapshot → Publication chain** | Identities are Dataplex timestamps. "Every push writes every Entry." Two agents cannot prove they read the same revision. | Three content identities plus immutable `publications` rows; identical republish is a no-op; unchanged-snapshot republish is a provenance event. | Adapter output on record: observation `85ea62a9…`, snapshot `f18befd0…`, publication `53bd1651…`; in-process pin `674153c5…`; Catalog pin `a25e1c0c…`. Same `context_ref` prefix, three publications, only BigQuery can hold the ledger. |
| 8 | **Delete-as-absence ledger vs `kcmd` no-delete** | Generic `kcmd push` creates or patches; `sync.ts` has "TODO: Handle creates and deletes". A superseded concept is served until someone deletes the whole EntryGroup. | Deletion is absence from the next snapshot; the ledger removes only owned entries. `current` mode excludes superseded concepts at query time. | `Customer revenue (legacy)`, out of force since 2026-06-20, excluded in 13 of 13 retrievals across sessions `f21ee192` and `1e6dfed7`. Catalog would still list it. |
| 9 | **LookupContext omitting custom aspects** | Per the post, LookupContext returns a pre-formatted YAML `context` and does not render custom aspects. The pin, the lifecycle fields, and the computation contract are invisible on the agent's main read path. | The Context Envelope carries `envelope_id`, manifest, `publication_id`, lifecycle mode, and the never-emit guard. | `gcloud dataplex entries lookup okf-derived-germany --view=ALL` returns `entrySource` only; there is no aspect on the entry, and no `okf` AspectType in the project. LookupContext on it yields the description string. |

Honest limits, to be printed on the page: the Catalog mapping itself (one entry per concept, `okf`
aspect, `overview` body, index and log entries, parent hierarchy) is shipped and complete; the RFC
adds pins and a ledger to it, not a rival projection. IAM on the EntryGroup is the only boundary
that is enforceable on the Catalog side; the ledger is a discipline.

## 3. Demo beats (`/rfc/full-demo/`, six beats, deep-linkable `#beat=1…6`)

| # | Beat | What the visitor sees | Source (all recorded; page is static) | Must prove |
|---|---|---|---|---|
| 1 | **Ask** | The real question and the 12 follow-ups from session `f21ee192`. Two traps: the dead metric, and over-claiming trust. | `agent_events` `USER_MESSAGE_RECEIVED` rows | Nothing is fictional. |
| 2 | **Observe** | One SQL query and its result: event histogram (Σ 180), the 24 tool calls, the `context_ref` on every result, the never-emit scan (0 hits). | `bq query` transcript, checked in | BQAA is observer-only; telemetry is not the bundle. |
| 3 | **Catalog path: where it dies** | `gcloud dataplex entries lookup okf-derived-germany --view=ALL` → description-only pin, no aspect. Then a LookupContext-shaped YAML with no verdict. Then session `04fa3d56`'s transcript: "You can trust the number because it is verified." | `gcloud` transcript; `agent_events` session `04fa3d56` | Discovery worked, trust failed. Catalog cannot carry the verdict, the pin, or the history. |
| 4 | **Sync (CLI)** | `okf-context sync` run: validate → observe → snapshot → plan (adds 8, removes 0) → `BQ_COMMITTED` → heads advanced → `CATALOG_STAMPED` on `okf-context-runtime` → status. | asciinema tape of the Phase A CLI | Sync is external, idempotent, explicit-state. Second run prints `no-op`. |
| 5 | **Serve (BigQuery)** | Three SQL results: `deployment_heads` for the deployment; retrieve `current` returning the six items and the one exclusion; `run_attested_computation` receipt `UNVERIFIABLE` with reason; a junk `context_ref` → `FAIL_CLOSED`. Session `f21ee192` transcript beside it: "No. The number is unproven." | `bq query` transcripts; existing CLI tape | Pin, SQL, lifecycle, honest verdict, fail-closed. |
| 6 | **Join** | One query joining `agent_events` to `publications` and `deployment_heads_history`: which session used which publication, and that the Catalog entry pins the oldest. | `bq query` transcript | The gap is a SQL result, not a slide. |

Beats 1, 2, 5 reuse material already on `/rfc/demo/`. Beats 3, 4, 6 are new. The existing
`okf-bqaa-cli.mp4` stays as the Observe → Publish → Next-agent tape; a new ~90 s tape covers 3 → 6
after dual LGTM (see `plan.md`).

## 4. Success criteria

- A cold reader can state the sync answer in one sentence after beat 4: "a CLI I run or schedule;
  commits to BigQuery first, stamps Catalog second; nothing managed does this today."
- Beat 3 contains one real failure or misread from a real session, quoted verbatim, with session id.
- Beat 6 is a real query result over `okf_rfc_demo` that a visitor could rerun with `bq query`.
- Every capability row in §2 is either shown on a beat or explicitly marked "RFC text only" on the page.
- Never-emit scan over every agent-facing payload on the page returns 0 hits.
- `python3 rfc/full-demo/tools/check_full_demo.py` (Phase C) exits 0: beats present, session ids and
  publication ids match the checked-in transcripts, no `ATTESTED` string outside the labelled Phase 4 shape.
- No change to OKF v0.2 core, `PROFILE.md` hashing, SDK PR 474, or the 180-row export.
