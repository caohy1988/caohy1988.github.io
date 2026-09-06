# BigQuery Graph spike — result report (2026-09-05/06, UTC)

Spike: project `acme_retail` (OKF v0.2, knowledge-catalog `31da799`) into BigQuery Graph; reproduce Lyon's deprecated-vs-current
landmine, impact analysis and stub backlog in GA GQL on Enterprise capacity; measure seed-plus-two-hop latency and honest cost.
Plans: `/tmp/okf-spikes/graph/{intent,spec,plan}.md`. Code and raw evidence: this directory. All timestamps UTC.

**Headline.** GQL runs on a short-lived Enterprise pay-as-you-go autoscaling reservation in this project (G1 measured, not
assumed). The Acme bundle compiles deterministically into a scoped, immutable publication (G2), and the deprecated
`metrics/gross-margin-legacy` anchor reaches the sanctioned `computations/gross-margin-period` SQL in exactly two `LINKS_TO`
hops through the current metric, with status, derived trust, freshness, provenance and the exact SQL digest matching the
relational oracle on the compared fields (G3). Impact analysis and stub backlog match the oracle set-for-set on names and
minimum hops (G4). Governance (G6) is **partial**: under the operator identity, a row-level policy removes the hidden
two-hop path inside the GQL walk and `CREATE PROPERTY GRAPH` accepts authorized views; the *no-hidden-identifier* claim is
INCONCLUSIVE for the RLS/authorized-view cases because the runtime leak detector was defective and full payloads were not
retained, and every case needing a second real principal is BLOCKED. Failed publish leaves the old pointer (G7); the
concurrent single-pin claim is PARTIAL. **G8 benchmark: 0 of 9 cells completed** — `acme_c1` reached 28/100 measured
requests before the driver was interrupted for cost control; C=5, C=10 and both synthetic scale corpora are NOT_RUN_BUDGET.
Nothing unmeasured is given a number. **This is retrieval evidence only.** No receipt verdict, no runtime ATTESTED label and
no connected KC discovery are claimed; combined delivery stays LOW per JOINT §4.

Review status: the fix pass at `aafdca3` closed Opus F1–F3; Astra's re-review found residual cache, lifecycle and evidence
defects. This second pass adds offline regressions and repairs the code and derived reports while preserving historical
raw records. Live INCONCLUSIVE/PARTIAL/NOT_RUN cases retain those labels; no new Enterprise measurements are claimed.

## G1 — capacity (MEASURED, PASSED)

See `capacity-gate.md`, `capacity.json`, `smoke_*.json`, `cleanup_manifest.json`.
No reservation, commitment or assignment existed in the three probed locations US / us-central1 / EU (no other locations
were probed); the project has no parent, so no inherited assignment is possible; the operator (a user principal with the
project Owner role; address redacted in committed evidence) holds the seven required permissions; billing is enabled.
Public SKU prices: Enterprise US multi-region pay-as-you-go **$0.06 / slot-hour**, on-demand $6.25 / TiB — the receipt is
`sku_receipt.json` (Cloud Billing Catalog API read by curl at 23:40Z; the later `capacity.py` read through an
AuthorizedSession got 403 SERVICE_DISABLED for the quota project, which is why `capacity.json.skus.rows` is empty). On-demand GQL fails with
`BigQuery Graph queries require a reservation with Enterprise or Enterprise Plus edition` (job
`okf_graph_smoke_ondemand_20260905234252`); `CREATE PROPERTY GRAPH` itself works on-demand. Smoke job
`okf_graph_smoke_ent_20260905234528_1` ran on `test-project-0728-467323:US.okf-graph-spike-20260905`, edition ENTERPRISE,
21,410 slot-ms. Reservation created 23:43:45, deleted 23:47:15, verified gone.

Operational findings: (1) **assignment propagation is not atomic** — after `bq mk --reservation_assignment`, jobs route
inconsistently between the reservation and on-demand for roughly two minutes: 120.9 s / 11 probes to six consecutive
successes in window `all-0012`, 140.4 s / 13 probes in window `all-0017`; window `integration-0007` saw one routed request
succeed and the next fall to on-demand. Individual failed probe job ids were not retained in those windows (the runner now
records every probe). The runner waits for six consecutive successes and retries a mis-routed job at most twice, recording
`routing_retries`. (2) The one cold zero-baseline smoke job took 40.5 s wall (start→end) — a single sample, not a
percentile. (3) Deleting a reservation requires deleting its assignment first; the `bq rm --reservation_assignment` id
format is `<reservation>.<assignment_id>`. (4) Window `integration-0009` was orphaned when the driver process was killed by
a session teardown; the independent safety watcher deleted the reservation (platform record: DELETE 00:11:10Z). Window
`all-0017` was interrupted by SIGINT for cost control and the in-process close did not log; the platform record shows its
DELETE at 00:27:27Z. Both closures are reconstructed in `cleanup_manifest.json` from `reservation_changes.json`
(INFORMATION_SCHEMA.RESERVATION_CHANGES), which shows a matching DELETE for every CREATE.

Cumulative reservation lifetime from the platform CREATE/DELETE pairs is 18.7 minutes (see `cleanup_manifest.json`), inside
the two-hour allowance.

## G2 — deterministic scoped projection (MEASURED, PASSED)

`compile.py` is a pure function of the pinned bytes: two compilations are byte-identical (`test_compile.py`), the
publication id is the digest of the source manifest (`pub_190192147fd7fd78`), every node/edge id embeds bundle and
publication, referential closure holds, unknown frontmatter (`not:` on `metrics/gross-margin`) is preserved, timestamps stay
as authored text, the attester is an `Artifact` and is never executed, `index.md` files stay manifest-only, and log entries
keep their dates and references. Acme: 44 nodes (9 Concept, 22 Section, 4 Source, 3 Actor, 2 Artifact, 4 LogEntry) and
109 edges; 0 stubs (the original backlog is empty, as Lyon also found). Seven edges are labelled `inferred` /
`root_fallback` because Acme's `executor:`/`attester:`/`sources[].resource` fields use bare root-relative paths.

Negative fixture `bundle_b` (same relative paths as Acme): scope stays separate (no node id collides), the missing targets
`metrics/not-written`, `computations/missing-comp` and the missing executor become non-executable stubs, the `../../../etc/passwd.md`
link is rejected and recorded, duplicate hits in one section produce distinct `LINKS_TO` provenance rows but one `MENTIONS`,
and the deprecated anchor with two stable same-type candidates yields `AMBIGUOUS` with no executable replacement.

Publication (`publish.py`, `publish_log.jsonl`): append → readback (44/109/22 sections/22 vectors, 0 dangling, 0 vector
digest mismatches) → `READY` → atomic `MERGE` of `active_publication` (21 s end-to-end on-demand, including
`ML.GENERATE_EMBEDDING` with `text-embedding-005`, 768 dims). Embeddings are a real semantic model, not the hash embedder.

## Method notes that bound the numbers

* Latency is caller wall time from request to fully assembled governed context, measured on this Mac against the US
  multi-region: embedding+seed (`VECTOR_SEARCH` with the query embedded in the same job), walk (one GQL job for all seeds),
  context and node fetch (two jobs in flight), assembly. Answer-generation LLM latency is excluded. Query-result cache is
  disabled. Stage clocks are caller-side round trips (submit → result), so they include client polling and network time;
  the statement that a request is "2–4 sequential job round trips of roughly a second each" is an **inference** from those
  clocks, not a measured BigQuery queue time.
* Percentiles are nearest-rank over all measured attempts including failures/timeouts; warmups are excluded; every attempt
  is in `requests.jsonl` before aggregation.
* Scale cells are namespace-isolated copies of Acme in their own datasets (`_x100`, `_x1000`) with vectors reused by text
  digest; they measure corpus/tenant overhead, not high-degree production graphs.
* Costs: slot attribution (`slot_ms/3.6e6 × $0.06`) is a resource-use estimate; the capacity bill is the per-minute
  autoscale timeline × $0.06/slot-hour with the platform's one-minute minimum and multiples of 50 slots; the two are not added.
  Billing-export reconciliation is pending (label: provisional).
