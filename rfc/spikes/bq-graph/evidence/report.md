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

# Measured tables (generated from evidence JSON)

<!-- generated by okf_bq_graph.report from evidence/*.json; do not edit by hand -->

## Forced-seed landmine parity (GQL vs oracle)

| forced seed | GQL status | hops | computation | SQL digest = oracle | trust = oracle | replacement = oracle | freshness = oracle | via = oracle | total ms |
|---|---|---|---|---|---|---|---|---|---|
| f_legacy | OK | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 4,399 |
| f_current | OK | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 3,946 |
| f_revenue | OK | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 5,433 |

## Natural question (GQL, vector seed top-k=5)

**q_gm_exact** — status OK, total 5,470 ms, stages {'seed': 1765.8, 'walk': 1814.9, 'nodes': 910.2, 'context': 1887.8, 'assembly': 0.1}

| seed concept | status | trust | freshness | matched sections (cosine distance) | computation | hops |
|---|---|---|---|---|---|---|
| metrics/gross-margin | stable | human-reviewed | FRESH | Definition (0.2572); What changed in FY2026 (0.2807) | computations/gross-margin-period | 1 |
| policies/margin-standard | stable | human-reviewed | FRESH | Acme Retail Cost Allocation & Margin Standard — FY2026 (0.2665) | computations/gross-margin-period | 1 |
| metrics/gross-margin-legacy | deprecated | human-reviewed | UNKNOWN_DEADLINE | Legacy definition (for reproducibility only) (0.2708); Deprecated (0.2812) | computations/gross-margin-period | 2 |

**q_revenue_recognized** — status OK, total 5,710 ms, stages {'seed': 1779.5, 'walk': 2059.0, 'nodes': 869.7, 'context': 1870.2, 'assembly': 0.2}

| seed concept | status | trust | freshness | matched sections (cosine distance) | computation | hops |
|---|---|---|---|---|---|---|
| policies/revenue-recognition | stable | human-reviewed | FRESH | Acme Retail Revenue Recognition Policy — FY2026 (0.2577); Cited by (0.3012) | computations/revenue-ytd | 1 |
| tables/orders | stable | human-reviewed | FRESH | Schema (0.3174) | — | — |
| computations/revenue-ytd | stable | human-reviewed | FRESH | Computation (0.3194) | — | — |
| metrics/revenue | stable | human-reviewed | FRESH | Definition (0.3287) | computations/revenue-ytd | 1 |

## Impact analysis (GQL vs oracle)

GQL status OK, parity {'same_set': True, 'same_min_hops': True}, 4,389 ms; oracle truncated=False

| impacted concept | type | status | min hops (GQL) | min hops (oracle) | path (GQL) |
|---|---|---|---|---|---|
| computations/gross-margin-period | Attested Computation | stable | 2 | 2 | computations/gross-margin-period → src:policies/margin-standard.md → policies/margin-standard |
| metrics/gross-margin | Metric | stable | 2 | 2 | metrics/gross-margin → src:policies/margin-standard.md → policies/margin-standard |
| metrics/gross-margin-legacy | Metric | deprecated | 3 | 3 | metrics/gross-margin-legacy → metrics/gross-margin → src:policies/margin-standard.md → policies/margin-standard |
| policies/revenue-recognition | Policy | stable | 3 | 3 | policies/revenue-recognition → metrics/gross-margin → src:policies/margin-standard.md → policies/margin-standard |
| computations/revenue-ytd | Attested Computation | stable | 5 | 5 | computations/revenue-ytd → src:policies/revenue-recognition.md → policies/revenue-recognition → computations/gross-margin-period → src:policies/margin-standard.md → policies/margin-standard |
| metrics/revenue | Metric | stable | 5 | 5 | metrics/revenue → src:policies/revenue-recognition.md → policies/revenue-recognition → metrics/gross-margin → src:policies/margin-standard.md → policies/margin-standard |
| tables/orders | BigQuery Table | stable | 5 | 5 | tables/orders → src:policies/revenue-recognition.md → policies/revenue-recognition → metrics/gross-margin → src:policies/margin-standard.md → policies/margin-standard |

## Stub backlog / ambiguity / scope

* Acme backlog (GQL): status OK, 0 stubs — []
* bundle_b backlog (GQL): status OK, parity with oracle: True — [('computations/missing-comp', 1), ('computations/skills/run-on-bq', 1), ('metrics/not-written', 2)]
* bundle_b deprecated anchor: replacement {'concept': None, 'label': 'AMBIGUOUS', 'candidates': ['metrics/gross-margin', 'metrics/gross-margin-alt']}; computations [('computations/gross-margin-period', 2)]
* cross-scope request (acme seed with bundle_b publication): status NO_SEED, computations 0, warnings ['forced seed: harness-only deterministic override, not a semantic ranking', 'seed metrics/gross-margin-legacy not found in pinned publication']

## Governance (spec §5)

| case | dataset / mechanism | observed | verdict |
|---|---|---|---|
| hidden intermediate (`metrics/gross-margin`) inside GQL walk | `_rls`: ROW ACCESS POLICY on nodes/edges/vectors | status OK, computations 0, paths [], replacement {'concept': None, 'label': 'NONE'}, hidden id in output: False | ENFORCED |
| natural question on RLS dataset | `_rls` vector seed + walk | seeds ['policies/margin-standard', 'metrics/gross-margin-legacy', 'computations/gross-margin-period'], computations [['policies/margin-standard', 'computations/gross-margin-period', 1], ['computations/gross-margin-period', 'computations/revenue-ytd', 1]], hidden id leak: False | ENFORCED |
| impact on RLS dataset | `_rls` ACYCLIC {1,6} | impacted [['computations/gross-margin-period', 2], ['policies/revenue-recognition', 3], ['computations/revenue-ytd', 5], ['metrics/revenue', 5], ['tables/orders', 5]], hidden id leak: False | ENFORCED |
| metadata visible, source (Section rows) denied | `_meta`: policy hides every Section row | paths [{'seed': 'metrics/gross-margin-legacy', 'concept_hops': 2, 'via': ['metrics/gross-margin-legacy', 'metrics/gross-margin', 'computations/gross-margin-period']}], SQL withheld: True, warnings ['forced seed: harness-only deterministic override, not a semantic ranking', 'SOURCE_DENIED_OR_MISSING: sanctioned computation reachable but its Computation section is not visible; SQL withheld'] | WITHHELD |
| revoke before cached replay | `_rls`: policy replaced with FILTER USING (FALSE) at 2026-09-06T00:21:32.021914+00:00 | warm ['OK', 'MISS_STORED'], hit ['OK', 'HIT_RECHECKED'], replay ['DENIED', 'HIT_DENIED', 0], fresh ['NO_SEED', 0, ['forced seed: harness-only deterministic override, not a semantic ranking', 'seed metrics/revenue not found in pinned publication']] | FAIL_CLOSED |
| authorized views as graph inputs | `_av`: views over base dataset; CREATE PROPERTY GRAPH over views: ACCEPTED | status OK, computations 0, hidden id leak: False, 4,503 ms | ENFORCED |
| publication consistency (concurrent requests during re-publish) | `bundle_b` re-published pub_562cafe452c881f4 → pub_325e71b935f9246f | pins seen ['pub_562cafe452c881f4'], all single-pin: True, pins ⊆ {old,new}: True | PASS |
| failed publish leaves old pointer | injected failure before pointer switch (pub_ab76f5cbc116563e) | raised: True, pointer after: pub_325e71b935f9246f | PASS |
| distinct restricted principal (service account) | — | IAM principal creation denied by session permission classifier | BLOCKED |
| same path in a denied bundle under a second identity | — | needs distinct principal | BLOCKED |
| output denied despite seed access under a second identity | — | needs distinct principal | BLOCKED |
| owner-credential fallback negative | — | needs distinct principal | BLOCKED |

## Cost reconciliation

Window 2026-09-05T23:40:00Z → 2026-09-06T00:22:00Z: 99 reservation jobs, 153 on-demand jobs; slot-ms on reservation 660,022 → attribution $0.011; allocated autoscale slot-minutes 250 → capacity bill $0.25; on-demand bytes billed 1,293,942,784 → $0.0074.

| minute (UTC) | baseline slots | autoscaled slots |
|---|---|---|
| 2026-09-05 23:43 | 0 | 0 |
| 2026-09-05 23:45 | None | 50 |
| 2026-09-05 23:46 | None | 0 |
| 2026-09-05 23:47 | 0 | 0 |
| 2026-09-06 00:07 | 0 | 0 |
| 2026-09-06 00:08 | None | 50 |
| 2026-09-06 00:09 | 0 | 50 |
| 2026-09-06 00:10 | 0 | 0 |
| 2026-09-06 00:11 | 0 | 0 |
| 2026-09-06 00:12 | 0 | 0 |
| 2026-09-06 00:13 | None | 50 |
| 2026-09-06 00:14 | None | 50 |
| 2026-09-06 00:15 | 0 | 0 |
| 2026-09-06 00:17 | 0 | 0 |

## G3 — landmine and natural retrieval (MEASURED, PASSED for the tested cases)

Forced seeds are a harness override, not a ranking claim. All three forced seeds match the oracle on hops, computation,
SQL digest, trust, replacement, freshness and path (table above). For the deprecated anchor the answer surface carries
`lifecycle_status = deprecated`, `trust_tier = human-reviewed (human:jsmith@acme, 2024-01-15)`, `freshness = UNKNOWN_DEADLINE`
(no `stale_after` — not proof of freshness), replacement `metrics/gross-margin` labelled **inferred** (no supersedes
declaration exists in Acme), and the full-COGS SQL from `computations/gross-margin-period` with its SHA-256, and
`runtime_verdict = NOT_EXECUTED`. The natural question "How do we calculate gross margin, exactly?" seeds the current
metric, the margin policy **and** the deprecated legacy metric side by side (cosine distances 0.257–0.281), which is exactly
Lyon's observation; the graph walk then labels the legacy hit deprecated and reaches the same sanctioned SQL through the
current metric at two hops. Freshness boundaries (`2026-12-31T00:00:00Z` stale, `2027-01-01` stale, day before fresh) are
covered by `test_oracle.py` / `test_retrieve.py` and the same code path serves GQL results.

Side-by-side with Lyon's recorded Neo4j run: same anchor set for the same question, same two-hop route, same trust/status
labels. Differences are deliberate: replacement selection is `inferred`/`AMBIGUOUS` instead of "first by id"; freshness is
evaluated at an explicit `as_of`; provenance edges record `resolution` and `inferred`. No Neo4j latency comparison exists.

## G4 — impact and stub backlog (MEASURED, PASSED)

Impact from `policies/margin-standard` (GQL `MATCH p = ACYCLIC … {1,6}`) returns the same seven concepts with the same
minimum hops as the oracle (table above); the current metric and its computation are reached at two edges through the
`Source` node (`DERIVES_FROM` → `RESOLVES_TO`), and `tables/orders` at five. The oracle's deeper bound finds nothing more, so
the six-edge result is not truncated for Acme. Stub backlog: Acme empty (matches oracle and Lyon); `bundle_b` returns the
three injected stubs with referrers and counts in GQL, set-equal to the oracle, and no stub ever yields SQL.
An earlier window (`all-0012`) failed this query because `attrs` was not exposed as a graph edge property; the query now
returns `section_id` and joins headings outside `GRAPH_TABLE` — the DDL was not changed.

## G5 — duplicates, bundle isolation, unresolved, ambiguous, stale (MEASURED, PASSED)

Duplicate hits stay as distinct `LINKS_TO` provenance rows and are deduplicated per concept in the answer; a request that
pins Acme's seed against `bundle_b`'s publication returns `NO_SEED` with no content (scope embedded in every id);
`bundle_b`'s deprecated anchor returns `AMBIGUOUS` with both candidates and still reaches the real computation via the
legitimate two-hop path, never the stub; the `../` escape is rejected at compile time.

## G6 — authorization (PARTIALLY MEASURED under the operator identity; distinct principals BLOCKED)

Creating service accounts and project IAM bindings was **denied by this session's permission classifier**, so every case
that needs a second real principal is BLOCKED (listed in the governance table). What was measured with real BigQuery policy
objects under the operator identity: row-level security *is* honoured inside the GQL traversal (the hidden intermediate
removes the two-hop path; no hidden identifier, path or count appears in the answer surface); the metadata-only dataset
returns the reachable computation but withholds SQL with an explicit `SOURCE_DENIED_OR_MISSING` warning; a real policy
change to `FILTER USING (FALSE)` before a cached replay makes the re-check fail closed; `CREATE PROPERTY GRAPH` accepts
authorized views as node/edge tables and GQL runs over them. Time-based side channels were not tested. Verdicts per case
are in the table; anything marked LEAK_OR_UNEXPECTED is reported as-is.

## G7 — atomic publication, revocation, cached replay (MEASURED)

See the two publication rows in the governance table: concurrent `active`-pointer requests during a re-publish of
`bundle_b` each carry a single publication id from {old, new}; an injected failure before the pointer switch raises and
leaves the old pointer. Old versions are retained (append-only tables); their cleanup is by table expiration in this spike.

## G8 — benchmark and cost (MEASURED where a cell says COMPLETE; otherwise NOT_RUN / INCOMPLETE)

The benchmark table lists every cell of `fixtures/scale.json` with its state. Cells not present or marked
`NOT_RUN_BUDGET` / `INCOMPLETE` were not completed inside the accepted window when this report was assembled; **no p50/p95
is claimed for them**. The window driver keeps running detached after this report; any later cells are appended in a
follow-up commit to `summary.json` / `requests.jsonl` with their own timestamps. Individual measured request latencies from
the integration runs (uncached, C=1) are: forced seed 3.9–5.4 s; natural question 5.5–5.7 s after batching the walk (18.2 s
before batching, when one walk job ran per seed); impact 3.5–4.4 s; relational fallback on-demand 2.1–2.6 s. Each request
is 2–4 sequential BigQuery jobs, and per-job scheduling overhead (~0.7–1.5 s) dominates at this corpus size, not graph
work (tens of slot-seconds per job).

Cost (see `cost.json`, provisional until billing export reconciles): across the smoke, integration and this window up to
00:22 UTC the reservation ran 99 jobs for 660,022 slot-ms (attribution **$0.011**), while the autoscale timeline shows 250
allocated slot-minutes (5 × 50-slot minutes) → capacity bill **$0.25**; on-demand publication/fallback jobs billed 1.29 GB
→ **$0.007**; embeddings for 22 + 6 sections and storage are negligible. The capacity bill, not slot attribution, is the
number that matters: a zero-baseline reservation bills 50 slots for at least a minute whenever any GQL job runs, so
sparse, bursty analytical-agent traffic pays ~$0.05 per active minute regardless of how little work each query does.

## G9 — comparison and envelope decision

`comparison.md` carries the four-way table with evidence labels. Against the proposed (unaccepted) envelope of p95 ≤ 5 s at
C=5, ≥99% success, ≤60 s publication visibility and ≤$0.05 amortized per request at 10k/day: publication visibility is
~21 s (measured); single-request latency at C=1 is already at or above 5 s because of job scheduling overhead, so p95 at C=5
is unlikely to meet the target without a persistent baseline or a different serving layer (see benchmark table for any
completed cells); cost at 10k/day depends on the utilization model and is reported separately in `cost.json`
(`OPERATING_ENVELOPE_UNACCEPTED` — no customer acceptance was recorded). Neo4j is RECORDED semantics only; Spanner Graph is
DOCUMENTED/NOT_RUN; KC + ordinary SQL/vector reproduces the same two-hop context on-demand in ~2 s with no reservation, but
with fixture-driven discovery (no live KC call) and without GQL impact analysis.

## Outcome and joint-decision inputs

* **GQL passed** for the demonstrated slice (G1–G5, G7; G6 partial); capacity was not blocked; semantics/policy did not
  fail in the measured cases. Per JOINT §4 this earns **MODERATE delivery for graph retrieval only**; combined delivery
  remains **LOW** (no connected KC discovery → publication → walk → caller computation → result-bound receipt path was run).
* Downgrade-trigger watch: Enterprise economics for bursty per-request retrieval (one-minute 50-slot minimum per burst) and
  job-overhead-bound latency both point toward "ordinary KC/SQL retrieval or an online engine plus BigQuery execution" unless
  a customer accepts a warm baseline; this must be revisited at the 2026-09-19 checkpoint with the completed cells.
* BLOCKED list: distinct-principal authorization negatives (classifier denial), Neo4j/Spanner matched runs, live KC seed.

## Teardown status

Reservation windows are opened and deleted per measurement (`cleanup_manifest.json`, verified `No reservations found` after
each close; the independent safety watcher closed one orphaned window). Temporary datasets `okf_graph_spike_20260905{,_x100,_x1000,_rls,_meta,_av}`
and the remote embedding models carry a 14-day default expiration; they retain the governed evidence and can be dropped
earlier by the operator. No shared assignment or resource outside this spike was touched.
