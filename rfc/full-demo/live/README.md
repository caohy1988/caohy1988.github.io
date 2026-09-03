# `live/` — captures read from `test-project-0728-467323` on 2026-09-03

Every file here was produced by one `bq`, `gcloud`, `curl`, or sample-script invocation run by the
**operator** (`raincoatrun@gmail.com`, project Owner, dataset OWNER, default gcloud configuration).
The Phase A service accounts (`okf-setup`, `okf-sync-writer-okf-rfc-demo`, `okf-runtime-reader`),
the custom role, the table-level grants, the boundary probe, and the negative checks of
`spec.md` §1.3 were **not** created for this capture; they are the Phase A follow-up. The page says
so on beat 4. `agent_events` received no DML and no agent was re-run.

Each `*.jobid` file holds the explicit `--job_id` its neighbour ran under. `bq_jobs_identity.json`
is the `INFORMATION_SCHEMA.JOBS_BY_USER` row set for every `okf_full_demo_%` job id, so the
`user_email` behind each query is on record.

## BigQuery (SELECT only unless stated)

| File | Statement | Result |
|---|---|---|
| `sessions_by_context_ref.json` | `sql/sessions_by_context_ref.sql` (v0, events only) | 5 rows |
| `session_f21ee192.json` | all rows for session `f21ee192-d989-4c38-894f-66b6b82eaf18` | 180 rows, 12 invocations, 9 event types |
| `session_04fa3d56.json` | all rows for session `04fa3d56-f2f1-413e-8c2b-ec116835af84` | 14 rows, 1 invocation |
| `session_1e6dfed7.json` | all rows for session `1e6dfed7-27ce-4c4d-b2e7-c45de7c241d1` | 15 rows, 1 invocation (second observe session) |
| `sessions_summary.json` | `sql/sessions_summary.sql`, row and tool-call count per session (aggregate; no row pull) | 4 sessions, 212 rows; the fourth session `a63c3e86-5897-40cc-bdf3-77bfcf750b12` (3 rows, 0 tool calls) is counted here and **not pulled** |
| `never_emit_scan.json` | `sql/never_emit_scan.sql` over all 27 `TOOL_COMPLETED` payloads | 0 hits on all 8 keys; 27 of 27 carry `context_ref` |
| `setup_runtime_tables.out` | **DDL + seed MERGEs**, `sql/setup_runtime_tables.sql`, run once as the operator (not yet as `okf-setup`) | 11 tables + 1 view created; 3 + 3 + 2 rows seeded |
| `beat6_attribution.json` | `sql/attribution_two_key.sql` STATEMENT 1 | 5 rows; band `attributed` Σ 14, band `receipt_only` Σ 13 |
| `beat6_demo_evidence.json` | `sql/attribution_two_key.sql` STATEMENT 2 | 2 rows |
| `beat5_serve_stmt1.json` | `sql/serve_probes.sql` STATEMENT 1, `deployment_heads` for `okf-rfc-demo` | 0 rows (no sync has run) |
| `beat5_serve_stmt2.json` | STATEMENT 2, `deployment_heads_history` as of 2026-06-30 | 0 rows (no sync has run) |
| `beat5_serve_stmt3.json` | STATEMENT 3, pin-or-fail-stale resolution for three handles | `NO_HEAD`, `AMBIGUOUS_LEGACY`, `FAIL_CLOSED` |
| `beat5_serve_stmt4.json` | STATEMENT 4, `publications` | 3 rows, all `seeded_pre_phase_a` |
| `beat5_serve_stmt5.json` | STATEMENT 5, `context_ref_resolution` view | 3 legacy rows, 0 phase_a rows |
| `bq_jobs_identity.json` | `INFORMATION_SCHEMA.JOBS_BY_USER` for `okf_full_demo_%` | every row `user_email = raincoatrun@gmail.com` |
| `provenance_sessions_summary.json` | `bq show -j` of the summary job: job id, executed query text, normalized SHA-256 of that text and of `sql/sessions_summary.sql`, result file hash and columns | binds job ↔ query ↔ SQL file ↔ result; **not** an identity source (identity comes only from `bq_jobs_identity.json`) |

## Knowledge Catalog (Dataplex Universal Catalog), `us-central1`

Legacy entry, read before any write:

| File | Command |
|---|---|
| `catalog_entry_okf-derived-germany.json` | `gcloud dataplex entries lookup …/entries/okf-derived-germany --view=ALL` (type `okf-concept`, **no aspects**) |
| `catalog_entry_type_okf-concept.json` | `gcloud dataplex entry-types describe okf-concept` |
| `catalog_entry_group_okf-rfc-demo.json` | `gcloud dataplex entry-groups describe okf-rfc-demo` |
| `catalog_entry_group_iam.json` | `gcloud dataplex entry-groups get-iam-policy okf-rfc-demo` (no bindings; `etag: ACAB`) |
| `lookup_context_okf-derived-germany.json` | `POST …/locations/us-central1:lookupContext {resources:[legacy entry]}` |
| `lookup_context_11_resources.json` | same call with 11 resources → `400 Only ten resources are supported at this time.` |
| `lookup_context_json_format.json` | same call with `options.format=json` |
| `lookup_context_missing_entry.json` | same call on a non-existent entry → `{}` |
| `lookup_context_two_entries.json` | same call on the legacy entry and the EntryGroup's own entry |
| `lookup_context_discovery.txt` | the `lookupContext` method and request/response schemas from the Dataplex v1 discovery document |

Shipped types, written by the operator for this page with the sample scripts from
`GoogleCloudPlatform/knowledge-catalog` @ `fbbc797` (`toolbox/mdcode/demo/okf`, `kcmd` built from
source because the checked-in lockfile pointed at a private registry):

| File | Command |
|---|---|
| `catalog_setup_transcript.txt` | `bun setup.ts --entry-group okf-rfc-demo` → created AspectType `okf` (13 fields) and EntryType `okf-bundle`; reused the existing EntryGroup |
| `catalog_push_transcript.txt` | `python3 examples/okf_bqaa_adapter/run.py` (SDK `main` @ `4f54b5c`) regenerated the derived bundle and reproduced `publication_id sha256:53bd1651…`; then `bun push.ts --bundle <that bundle>` |
| `catalog_entries_list_after_push.json` | `gcloud dataplex entries list --entry-group=okf-rfc-demo` → 10 entries: 8 `okf-bundle`, the legacy `okf-concept`, the group entry |
| `catalog_shipped_entry_metric_viewALL.json` | `entries lookup …/entries/metrics/active-customer-revenue --view=ALL` (real `okf` aspect + `overview`) |
| `catalog_shipped_entry_computation_viewALL.json` | same for `computations/active-customer-revenue-by-region-and-quarter` |
| `catalog_shipped_entry_legacy_metric_viewALL.json` | same for `metrics/customer-revenue-legacy` (`status: deprecated`, still discoverable) |
| `lookup_context_shipped_metric.json` | `lookupContext` on the metric entry: `type`, `description`, `overview`, `labels`; **no `okf` fields** |
| `lookup_context_shipped_computation.json` | `lookupContext` on the computation entry: same shape, no `runtime` / `parameters` / `executor` / `attester` |
| `search_entries_okf_type_metric.json` | `POST …/locations/global:searchEntries {query: aspect:…okf.okf_type="Metric"}` → both metrics, including the deprecated one |
| `search_entries_okf_status_deprecated.json` | `searchEntries {query: aspect:…okf.status=deprecated}` → the legacy metric |
| `catalog_aspect_type_okf.json`, `catalog_entry_type_okf-bundle.json` | `aspect-types describe okf`, `entry-types describe okf-bundle` |
| `catalog_aspect_types_us-central1.json`, `catalog_entry_types_us-central1.json` | type lists after setup |

The legacy entry `okf-derived-germany` was re-read after the push and is byte-identical to the
pre-push snapshot (`updateTime 2026-09-02T23:03:22Z`, still no aspects). It stays labelled **prior**.

## Not captured (and why)

- No `okf-context-runtime` aspect, no `BQ_COMMITTED`, no `CATALOG_STAMPED`, no `no-op`: the
  `okf-context sync` CLI does not exist yet (Phase A). Nothing here pretends otherwise.
- No `PERMISSION_DENIED` checks: the three service accounts were not created. Deferred to Phase A.
- No `FAIL_STALE`: it needs a head in `deployment_heads` to compare against, and there is none.
  `FAIL_CLOSED` (unbound handle) and `AMBIGUOUS_LEGACY` (the double-bound legacy handle) are real
  query results; `NO_HEAD` is what a bound handle resolves to today.
