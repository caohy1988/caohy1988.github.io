# BigQuery Graph spike — result report (2026-09-05/06, UTC)

Spike: project `acme_retail` (OKF v0.2, knowledge-catalog `31da799`) into BigQuery Graph; reproduce Lyon's deprecated-vs-current
landmine, impact analysis and stub backlog in GA GQL on Enterprise capacity; measure seed-plus-two-hop latency and honest cost.
Plans: `/tmp/okf-spikes/graph/{intent,spec,plan}.md`. Code and raw evidence: this directory. All timestamps UTC.

**Headline.** GQL runs on a short-lived Enterprise pay-as-you-go autoscaling reservation in this project (G1 measured, not
assumed). The Acme bundle compiles deterministically into a scoped, immutable publication (G2), and the deprecated
`metrics/gross-margin-legacy` anchor reaches the sanctioned `computations/gross-margin-period` SQL in exactly two `LINKS_TO`
hops through the current metric, with status, derived trust, freshness, provenance and the exact SQL digest matching the
relational oracle (G3). Impact analysis and stub backlog match the oracle set-for-set (G4). Row-level security is honoured
inside a GQL traversal and authorized views are accepted as graph inputs (G6, operator identity only). Publication switch
and failed-publish behaviour are as specified (G7). Benchmark and cost cells are in the tables below with their sample sizes;
anything not measured is labelled NOT_RUN or BLOCKED, never zero. **This is retrieval evidence only.** No receipt verdict,
no runtime ATTESTED label and no connected KC discovery are claimed; combined delivery stays LOW per JOINT §4.

## G1 — capacity (MEASURED, PASSED)

See `capacity-gate.md`, `capacity.json`, `smoke_*.json`, `cleanup_manifest.json`.
No reservation, commitment or assignment existed in US / us-central1 / EU; the project has no parent, so no inherited
assignment is possible; the operator holds the seven required permissions; billing is enabled. Public SKU (Billing Catalog
API): Enterprise US multi-region pay-as-you-go **$0.06 / slot-hour**; on-demand $6.25 / TiB. On-demand GQL fails with
`BigQuery Graph queries require a reservation with Enterprise or Enterprise Plus edition` (job
`okf_graph_smoke_ondemand_20260905234252`); `CREATE PROPERTY GRAPH` itself works on-demand. Smoke job
`okf_graph_smoke_ent_20260905234528_1` ran on `test-project-0728-467323:US.okf-graph-spike-20260905`, edition ENTERPRISE,
21,410 slot-ms. Reservation created 23:43:45, deleted 23:47:15, verified gone.

Operational findings: (1) **assignment propagation is not atomic** — after `bq mk --reservation_assignment`, jobs route
inconsistently between the reservation and on-demand for roughly two minutes (measured 121 s to six consecutive successes
in the last window; an earlier window saw one success followed by an on-demand failure). The orchestrator now waits for six
consecutive successes and the client retries a mis-routed job at most twice, recording `routing_retries`. (2) A cold
zero-baseline reservation took ~40 s wall for the first trivial GQL job (autoscale to 50 slots). (3) Deleting a reservation
requires deleting its assignment first; the `bq rm --reservation_assignment` id format is `<reservation>.<assignment_id>`.
(4) One orphaned window (`integration-0007`/`safety-0011`) was closed by the independent safety watcher 3.5 minutes after the
driver process was killed, which is exactly why the plan required an independent watchdog.

Cumulative reservation time across windows is recorded in `cleanup_manifest.json` and stays inside the two-hour allowance.

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
  disabled. Each BigQuery job carries ~0.7–1.5 s of scheduling overhead, so a request is 2–4 sequential job latencies.
* Percentiles are nearest-rank over all measured attempts including failures/timeouts; warmups are excluded; every attempt
  is in `requests.jsonl` before aggregation.
* Scale cells are namespace-isolated copies of Acme in their own datasets (`_x100`, `_x1000`) with vectors reused by text
  digest; they measure corpus/tenant overhead, not high-degree production graphs.
* Costs: slot attribution (`slot_ms/3.6e6 × $0.06`) is a resource-use estimate; the capacity bill is the per-minute
  autoscale timeline × $0.06/slot-hour with the platform's one-minute minimum and multiples of 50 slots; the two are not added.
  Billing-export reconciliation is pending (label: provisional).
