# RFC full path, one live run: publish in BigQuery, then consume (report, 2026-09-15)

**Result: `E2E_PUBLISH_CONNECTED`** for run `kp-20260915t082018z-0387` (08:20:18–08:32:49 UTC).

One invocation ran the RFC's order on live GCP APIs in `test-project-0728-467323`: the Acme bundle was published in BigQuery (append, full-row readback, `READY`, atomic head `MERGE`), a Catalog entry pinned to that publication was written from the `READY` rows, and the restricted requester then discovered it, pinned it, retrieved the declared calculation, was authorized, ran the receipt and was revoked. It is **not** readiness: one run, synthetic data, relational SQL rather than BigQuery Graph, the SDK's own verifier. See "What this run does not establish".

- **Runner:** `okf_bq_graph.publish_connected/0.1.0` (consume half `okf_bq_graph.connected/0.1.0`) at spike commit `c075801`.
- **CLI and agent:** [`caohy1988/okf-connected-e2e`](https://github.com/caohy1988/okf-connected-e2e) `7773909` (0.2.0), model `gemini-3.8-flash` on Vertex AI (`global`).
- **Record:** [`publish-connected/kp-20260915t082018z-0387/publish_connected_live.json`](publish-connected/kp-20260915t082018z-0387/publish_connected_live.json); publish journal, ownership and cleanup receipts under [`publish-connected/kp-20260915t082018z-0387/publish/`](publish-connected/kp-20260915t082018z-0387/publish/).
- **Connected record:** [`connected_live.json`](publish-connected/kp-20260915t082018z-0387/connected/e2e-20260915t082049z-34e6ed72/connected_live.json) (consume run `e2e-20260915t082049z-34e6ed72`).
- **Agent transcript:** [`agent_transcript.json`](publish-connected/kp-20260915t082018z-0387/agent_transcript.json). **Terminal recording:** [`recording_transcript.txt`](publish-connected/kp-20260915t082018z-0387/recording_transcript.txt), tape at [`/rfc/demo/#connected-e2e`](../../../demo/#connected-e2e) (real live run; idle waits compressed to 3 s).

## The RFC path, beat by beat

| RFC beat | What ran | Evidence in this run |
|---|---|---|
| Author / publish (BigQuery; detailed RFC §04 authority, §05 states) | compile pinned source → run-owned dataset `okf_kp_publish_kp_20260915t082018z_0387` → load rows → full-row readback → `READY` → `MERGE active_publication` | `READY` `pub_190192147fd7fd78` (44 nodes, 109 edges, 22 sections); head `None` → `pub_190192147fd7fd78` (SWITCHED), merge job `okf_cc_kp_20260915t082018z_0387_merge_head_b402d3731b67` |
| Catalog discovery projection (§05 `KC_APPLIED`) | owned entry written only after the head advanced; pin generated from the `READY` rows | readback `OK` |
| Discover (Catalog) | the requester's own `entries.list` + `entries.get(view=ALL)` of that entry | consumed-publication check `MATCH` (pin names this publication and dataset; head observed on it) |
| Pin + retrieve a fixed context | exact `READY` publication, head observed not followed; governed retrieval on the published tables; payload guard; bind | approved decision `RELEASED` / MET |
| Evaluate current access | restricted requester; unauthorized output denied; revocation | fresh request after revocation `CATALOG_ERROR`, bypass publication `ERROR`, bypass retrieval `DENIED`, authorization `DENIED`, receipt launches after revocation 0 |
| Validate the calculation | SDK receipt CLI under the requester; result-bound receipt | receipt `VERIFIED`; substitution case `REFUSED` |
| Enforcing consumer | releases only on the checks above | `[LIVE] Gross margin: $400.00 USD · VERIFIED` |

## BigQuery publish: every author job

All jobs were submitted by the operator under driver-chosen ids (journaled before dispatch) and read back with `jobs.get` after the run: author identity **`BOUND`** over 19 jobs; unresolved publish jobs: 0.

| # | Role | BigQuery job id | State | Rows |
|---|---|---|---|---|
| 2 | `snapshot_original_head` | `okf_cc_kp_20260915t082018z_0387_snapshot_original_head_a149bea8e896` | DONE | 1 |
| 5 | `create_table` | `okf_cc_kp_20260915t082018z_0387_create_table_04cf3f134493` | DONE |  |
| 6 | `create_table` | `okf_cc_kp_20260915t082018z_0387_create_table_d3d7d4872ab8` | DONE |  |
| 7 | `create_table` | `okf_cc_kp_20260915t082018z_0387_create_table_9c2317a5ff39` | DONE |  |
| 8 | `create_table` | `okf_cc_kp_20260915t082018z_0387_create_table_892b982f75f1` | DONE |  |
| 9 | `publication_exists` | `okf_cc_kp_20260915t082018z_0387_publication_exists_04de1f209885` | DONE | 0 |
| 10 | `load_nodes` | `okf_cc_kp_20260915t082018z_0387_load_nodes_7f0d27d40667` | DONE |  |
| 11 | `load_edges` | `okf_cc_kp_20260915t082018z_0387_load_edges_21df42ad11ac` | DONE |  |
| 12 | `readback_nodes` | `okf_cc_kp_20260915t082018z_0387_readback_nodes_1dad6332bfb8` | DONE | 44 |
| 13 | `readback_edges` | `okf_cc_kp_20260915t082018z_0387_readback_edges_d21456ca6d2c` | DONE | 109 |
| 14 | `insert_publication` | `okf_cc_kp_20260915t082018z_0387_insert_publication_4ffc4d91d100` | DONE |  |
| 15 | `publication_status` | `okf_cc_kp_20260915t082018z_0387_publication_status_fc1b6390442f` | DONE | 1 |
| 16 | `read_head` | `okf_cc_kp_20260915t082018z_0387_read_head_c65816785e7e` | DONE | 0 |
| 17 | `merge_head` | `okf_cc_kp_20260915t082018z_0387_merge_head_b402d3731b67` | DONE |  |
| 18 | `read_head` | `okf_cc_kp_20260915t082018z_0387_read_head_9945996bc0ff` | DONE | 1 |
| 19 | `pin_source_publication` | `okf_cc_kp_20260915t082018z_0387_pin_source_publication_f4f9fcaf50e0` | DONE | 1 |
| 20 | `pin_source_seed` | `okf_cc_kp_20260915t082018z_0387_pin_source_seed_09bfac7145be` | DONE | 1 |
| 24 | `read_head` | `okf_cc_kp_20260915t082018z_0387_read_head_85a953aabf4a` | DONE | 1 |
| 26 | `reread_original_head` | `okf_cc_kp_20260915t082018z_0387_reread_original_head_3196e0d747a7` | DONE | 1 |

Non-job writes (dataset and Catalog entry): `create_dataset` DONE, `create_entry` DONE, `delete_entry` DONE, `delete_dataset` DONE.

**RFC §05 state trace** (simplified protocol, see limits):

| State | At (UTC) | Jobs establishing it |
|---|---|---|
| `PLANNED` | 08:20:18 | — |
| `PREPARING` | 08:20:24 | `okf_cc_kp_20260915t082018z_0387_snapshot_original_head_a149bea8e896`, `okf_cc_kp_20260915t082018z_0387_create_table_04cf3f134493`, `okf_cc_kp_20260915t082018z_0387_create_table_d3d7d4872ab8`, `okf_cc_kp_20260915t082018z_0387_create_table_9c2317a5ff39`, `okf_cc_kp_20260915t082018z_0387_create_table_892b982f75f1` |
| `BQ_STAGED` | 08:20:37 | `okf_cc_kp_20260915t082018z_0387_publication_exists_04de1f209885`, `okf_cc_kp_20260915t082018z_0387_load_nodes_7f0d27d40667`, `okf_cc_kp_20260915t082018z_0387_load_edges_21df42ad11ac`, `okf_cc_kp_20260915t082018z_0387_readback_nodes_1dad6332bfb8`, `okf_cc_kp_20260915t082018z_0387_readback_edges_d21456ca6d2c`, `okf_cc_kp_20260915t082018z_0387_insert_publication_4ffc4d91d100` |
| `BQ_COMMITTED` | 08:20:43 | `okf_cc_kp_20260915t082018z_0387_publication_status_fc1b6390442f`, `okf_cc_kp_20260915t082018z_0387_read_head_c65816785e7e`, `okf_cc_kp_20260915t082018z_0387_merge_head_b402d3731b67`, `okf_cc_kp_20260915t082018z_0387_read_head_9945996bc0ff` |
| `KC_APPLIED` | 08:20:46 | `okf_cc_kp_20260915t082018z_0387_pin_source_publication_f4f9fcaf50e0`, `okf_cc_kp_20260915t082018z_0387_pin_source_seed_09bfac7145be` |
| `COMPLETE` | 08:20:47 | `okf_cc_kp_20260915t082018z_0387_read_head_85a953aabf4a` |

**`READY` row** (full-row readback checks: dangling, distinct, edge_rows, edges_sha256, node_rows, nodes_sha256, section_hashes all true): `source_pin` `31da799a9aef176df12e91abbd119ea9385b75ec`, `nodes_sha256` `47a1278ef2bc4e2c…`, `edges_sha256` `95a193a0c41354a1…`, `ready_at` 2026-09-15T08:20:35.758988+00:00.

**Catalog entry:** `projects/test-project-0728-467323/locations/us-central1/entryGroups/okf-rfc-demo/entries/acme-retail-kp-publish/kp-20260915t082018z-0387/metrics/gross-margin`.

## Consume: the connected cases against that publication

| Case | Decision | Acceptance |
|---|---|---|
| `connected-approved` | RELEASED | MET |
| `connected-denied-intermediate` | REFUSED | MET |
| `connected-revocation` | REFUSED | MET |
| `connected-sql-substitution` | REFUSED | MET |
| `connected-unauthorized-output` | REFUSED | MET |

Requester identity `BOUND` (graph 46 jobs BOUND, policy_admin 9 jobs BOUND, receipt 2 jobs BOUND, requester_probe 1 jobs BOUND); unresolved jobs 0; teardown {'broker': 'VERIFIED', 'catalog': 'VERIFIED'}. Catalog grant observed after 71 s; caller is requester: True.

Requester job inventory: 46 graph/store jobs, receipt jobs `okf_rcpt_a783c736b3ac936351bef069_22e00a1dd6cb4fc8`, `okf_rcpt_d2472cd6fef3b214eb39c20d_2a2706019e808fcb`.

## Did the consumer serve what was published?

`MATCH`: catalog_ok=True, entry_is_owned=True, head_is_published=True, pin_dataset=True, pin_publication=True, publication_ok=True, store_dataset=True.

## Teardown

Originals (the long-lived entry and head) re-read: `UNCHANGED`. Cleanup `COMPLETE`: entry ['kp-20260915t082018z-0387', 'metrics', 'gross-margin'] deleted=True absent=True; dataset okf_kp_publish_kp_20260915t082018z_0387 deleted=True absent=True. The rows are gone; the job metadata above stays readable.

## RFC coverage

| RFC section | This run |
|---|---|
| Detailed §04 Authority (BigQuery head serving authority; Catalog discovery projection) | shown once: publish and head switch in BigQuery, Catalog pin written after from `READY` rows |
| Detailed §05 Cross-service consistency | states `BQ_STAGED → BQ_COMMITTED → KC_APPLIED → COMPLETE` recorded once on a simplified protocol (not `sync_id`/`deployment_heads`/`*_current`/lag SLO) |
| Detailed §04 "a Catalog-discovered seed carries the publication it describes" | shown: the consumer served exactly the published id in the owned dataset |
| Landing "Retrieve a fixed context" | shown on plain SQL (relational fallback) |
| Landing "Evaluate current access" | shown on plain SQL: denial, revocation with fresh request / cached-pin bypass / stored receipt refused |
| Landing "Validate the calculation" | shown with the SDK's own verifier and a requester-held key |
| Landing "The three as one path" | shown once, now starting from its own BigQuery publish |
| Landing "What is still open" | still open: the same inside graph queries, an independent attester, repeated runs, cost/latency |

## What this run does not establish

- Graph: retrieval and access ran on relational SQL, not BigQuery Graph / GQL; access inside graph queries is still open.
- Attestation: the SDK example's own verifier with a requester-held key; no independent attester.
- Knowledge revision: the publication id is content-addressed from the pinned source, so this run deployed the same id the long-lived spike dataset holds, into a fresh run-owned dataset with fresh rows and jobs. It is a new deployment, not a new revision of the knowledge (a new revision changes the source pin, which the receipt fixture's lineage label binds).
- §05 protocol: simplified to one owned dataset with `active_publication`; no `sync_id` staging, `deployment_heads(_history)`, `*_current` views, `published_snapshot_id`, `KC_RECONCILING` lag SLO, or `okf-context`/`kcmd` package.
- Access setup: the harness grants the requester Catalog viewer on the entry group and dataset reads; the denied-intermediate case uses the injected legacy seed on the long-lived `_rls` copy of the same publication id.
- Sample: n = 1, synthetic Acme data, no cost or latency benchmark. Earlier runs stay as recorded: `e2e-20260915t070643z-9ddaf35f` (consume-only, `E2E_CONNECTED`) and `e2e-20260915t065449z-98e21004` (`E2E_BROKEN`).
