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

# Measured tables (generated from evidence JSON)

<!-- generated by okf_bq_graph.report from evidence/*.json; do not edit by hand -->

## Forced-seed landmine parity (GQL vs oracle)

| forced seed | GQL status | hops | computation | SQL digest = oracle | trust = oracle | replacement = oracle | freshness = oracle | via = oracle | provenance resources = oracle (post hoc) | total ms |
|---|---|---|---|---|---|---|---|---|---|---|
| f_legacy | OK | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (resource set) | 4,399 |
| f_current | OK | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (resource set) | 3,946 |
| f_revenue | OK | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (resource set) | 5,433 |

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

| case | dataset / mechanism | observed (recorded, unmodified) | recorded verdict / flag | post-hoc note (does not change the record) | published label |
|---|---|---|---|---|---|
| hidden intermediate (`metrics/gross-margin`) inside GQL walk | `_rls`: ROW ACCESS POLICY on nodes/edges/vectors | status OK, computations 0, paths [], replacement {'concept': None, 'label': 'NONE'} | `leaks_hidden_id=True`, `LEAK_OR_UNEXPECTED` | INCONCLUSIVE — runtime flag came from a substring detector that also matches `-legacy`; full payload not retained; no re-run | INCONCLUSIVE (path removal corroborated: computations 0, paths [], replacement NONE, RLS probe hidden=0; no-leak claim unverified) |
| natural question on RLS dataset | `_rls` vector seed + walk | seeds ['policies/margin-standard', 'metrics/gross-margin-legacy', 'computations/gross-margin-period'], computations [['policies/margin-standard', 'computations/gross-margin-period', 1], ['computations/gross-margin-period', 'computations/revenue-ytd', 1]] | `leaks_hidden_id=True`, `None` | INCONCLUSIVE — runtime flag came from a substring detector that also matches `-legacy`; full payload not retained; no re-run | INCONCLUSIVE (no-leak claim unverified) |
| impact on RLS dataset | `_rls` ACYCLIC {1,6} | impacted [['computations/gross-margin-period', 2], ['policies/revenue-recognition', 3], ['computations/revenue-ytd', 5], ['metrics/revenue', 5], ['tables/orders', 5]] | `leaks_hidden_id=False`, `None` | runtime flag false (substring detector); full payload not retained | ENFORCED (hidden concept absent from impacted set; recorded flag false) |
| metadata visible, source (Section rows) denied | `_meta`: policy hides every Section row | paths [{'seed': 'metrics/gross-margin-legacy', 'concept_hops': 2, 'via': ['metrics/gross-margin-legacy', 'metrics/gross-margin', 'computations/gross-margin-period']}], SQL withheld: True | `WITHHELD` | SQL null with `SOURCE_DENIED_OR_MISSING` warning; operator identity | WITHHELD |
| revoke before cached replay (all rows) | `_rls`: policy replaced with FILTER USING (FALSE) at 2026-09-06T00:21:32.021914+00:00 | warm ['OK', 'MISS_STORED'], hit ['OK', 'HIT_RECHECKED'], replay ['DENIED', 'HIT_DENIED', 0], fresh ['NO_SEED', 0, ['forced seed: harness-only deterministic override, not a semantic ranking', 'seed metrics/revenue not found in pinned publication']] | `FAIL_CLOSED` | edge-only revocation was NOT exercised live; outer SQL now projects traversal edge_ids, version-2 cache requires complete dependencies, and incomplete/legacy entries trigger fresh retrieval; second-hop revocation has offline coverage using actual result columns, not new live evidence | FAIL_CLOSED (all-rows case only) |
| authorized views as graph inputs | `_av`: views over base dataset; graph-input acceptance: ACCEPTED | status OK, computations 0, 4,503 ms | `leaks_hidden_id=True`, `LEAK_OR_UNEXPECTED` | INCONCLUSIVE — runtime flag came from a substring detector that also matches `-legacy`; full payload not retained; no re-run; same operator identity, no second principal | INCONCLUSIVE (no-leak claim unverified) |
| publication consistency (concurrent requests during re-publish) | `bundle_b` re-published pub_562cafe452c881f4 → pub_325e71b935f9246f | pins seen ['pub_562cafe452c881f4'], all single-pin: True | recorded by scope-only checker (invalid: could not detect a mixed payload) | PARTIAL — six requests all reported the old pin by scope; payload-level single-pin was not verifiable at measurement time; checker replaced and unit-tested offline, not re-measured | PARTIAL |
| failed publish leaves old pointer | injected failure before pointer switch (pub_ab76f5cbc116563e) | raised: True, pointer after: pub_325e71b935f9246f | `True` | pointer read back after the raised failure | PASS |
| distinct restricted principal (service account) | — | IAM principal creation denied by session permission classifier | — | — | BLOCKED |
| same path in a denied bundle under a second identity | — | needs distinct principal | — | — | BLOCKED |
| output denied despite seed access under a second identity | — | needs distinct principal | — | — | BLOCKED |
| owner-credential fallback negative | — | needs distinct principal | — | — | BLOCKED |

The four BLOCKED rows above are the 2026-09-05 record and are kept as recorded. On 2026-09-06 the same cases (plus revocation before cached replay) were measured under the receipt spike's existing restricted service account via impersonation on the relational fallback engine: 5/5 MEASURED, teardown VERIFIED; inside a GQL traversal they remain BLOCKED (Enterprise window gate). Evidence: `evidence/authz_cases.json`; summary in `comparison.md` row 1.

## Benchmark cells (spec §6)

| run | cell | corpus | C | n measured / target | state | ok rate | errors | timeouts | p50 all (ms) | p95 all (ms) | max (ms) | p50 seed | p50 walk | p50 context | p50 nodes | jobs | slot-ms | slot attribution USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| legacy-unlabeled | acme_c1 | acme | 1 | 28 / 100 | INCOMPLETE | 100.0% | 0 | 0 | 4,384 | 5,441 | 10,869 | 1,389 | 2,068 | 1,278 | 802 | 101 | 609,261 | 0.0102 |
| legacy-unlabeled | acme_c5 | acme | 5 | 0 / 100 | NOT_RUN_BUDGET | — | 0 | 0 | — | — | — | — | — | — | — | 0 | 0 | 0.0000 |
| legacy-unlabeled | x100_c1 | copies_100 | 1 | 0 / 100 | NOT_RUN_BUDGET | — | 0 | 0 | — | — | — | — | — | — | — | 0 | 0 | 0.0000 |
| legacy-unlabeled | x100_c5 | copies_100 | 5 | 0 / 100 | NOT_RUN_BUDGET | — | 0 | 0 | — | — | — | — | — | — | — | 0 | 0 | 0.0000 |
| legacy-unlabeled | acme_c10 | acme | 10 | 0 / 100 | NOT_RUN_BUDGET | — | 0 | 0 | — | — | — | — | — | — | — | 0 | 0 | 0.0000 |
| legacy-unlabeled | x1000_c1 | copies_1000 | 1 | 0 / 100 | NOT_RUN_BUDGET | — | 0 | 0 | — | — | — | — | — | — | — | 0 | 0 | 0.0000 |
| legacy-unlabeled | x1000_c5 | copies_1000 | 5 | 0 / 100 | NOT_RUN_BUDGET | — | 0 | 0 | — | — | — | — | — | — | — | 0 | 0 | 0.0000 |
| legacy-unlabeled | x1000_c10 | copies_1000 | 10 | 0 / 100 | NOT_RUN_BUDGET | — | 0 | 0 | — | — | — | — | — | — | — | 0 | 0 | 0.0000 |
| legacy-unlabeled | x100_c10 | copies_100 | 10 | 0 / 100 | NOT_RUN_BUDGET | — | 0 | 0 | — | — | — | — | — | — | — | 0 | 0 | 0.0000 |

## Cost reconciliation (provisional)

Window 2026-09-05T23:40:00Z → 2026-09-06T00:35:00Z. Named reservation `test-project-0728-467323:US.okf-graph-spike-20260905`: 323 jobs, 1,988,844 slot-ms → attribution $0.0331. Other pool(s) ['default-pipeline']: 26 jobs, 86,674 slot-ms (not billed at the Enterprise rate here). On-demand: 171 jobs, 1,293,942,784 bytes billed → $0.0074 at list rate (free tier not applied). Charged autoscale slot-seconds from RESERVATIONS_TIMELINE: 21,750 → **$0.3625** capacity bill estimate (baseline slot-seconds 0); legacy snapshot sum 850 slot-minutes shown for comparison only. Timeline last row: 2026-09-06 00:27:00+00:00.

| minute (UTC) | baseline slots | autoscaled slots (snapshot) | charged autoscale slot-seconds |
|---|---|---|---|
| 2026-09-05 23:43 | 0 | 0 | 0 |
| 2026-09-05 23:45 | None | 50 | 1450 |
| 2026-09-05 23:46 | None | 0 | 0 |
| 2026-09-05 23:47 | 0 | 0 | 0 |
| 2026-09-06 00:07 | 0 | 0 | 0 |
| 2026-09-06 00:08 | None | 50 | 600 |
| 2026-09-06 00:09 | 0 | 50 | 2850 |
| 2026-09-06 00:10 | 0 | 0 | 0 |
| 2026-09-06 00:11 | 0 | 0 | 0 |
| 2026-09-06 00:12 | 0 | 0 | 0 |
| 2026-09-06 00:13 | None | 50 | 850 |
| 2026-09-06 00:14 | None | 50 | 450 |
| 2026-09-06 00:15 | 0 | 100 | 2400 |
| 2026-09-06 00:17 | 0 | 0 | 0 |
| 2026-09-06 00:18 | None | 50 | 500 |
| 2026-09-06 00:19 | None | 50 | 250 |
| 2026-09-06 00:20 | None | 100 | 600 |
| 2026-09-06 00:21 | None | 50 | 300 |
| 2026-09-06 00:22 | None | 50 | 2900 |
| 2026-09-06 00:23 | None | 50 | 2750 |
| 2026-09-06 00:24 | None | 50 | 2250 |
| 2026-09-06 00:25 | None | 50 | 1900 |
| 2026-09-06 00:26 | None | 50 | 1700 |
| 2026-09-06 00:27 | 0 | 0 | 0 |

## G3 — landmine and natural retrieval (MEASURED, PASSED for the tested cases)

Forced seeds are a harness override, not a ranking claim. All three forced seeds match the oracle on the compared fields —
hops, computation, SQL digest, trust tier, replacement, freshness verdict, path — and on the provenance *resource set*
(post-hoc column). Full provenance parity is **incomplete**: the GQL answer carries resource, title, declaration and
resolution, but not the declaration-scoped signals (`usage_count`, `usage_window`) or `resolves_to`, which the oracle
includes; those are not graph properties and would need a join to the edges/nodes tables. For the deprecated anchor the answer surface carries
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
minimum hops as the oracle (table above; names and minimum hops are compared, the oracle's trust/truncation fields are not); the current metric and its computation are reached at two edges through the
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

## G6 — authorization (PARTIAL; operator identity only; distinct principals BLOCKED)

Creating service accounts and project IAM bindings was **denied by this session's permission classifier**, so every case
that needs a second real principal is BLOCKED (listed in the governance table). Measured with real BigQuery policy objects
under the operator identity:

* **Hidden intermediate inside the GQL walk (RLS):** the two-hop path disappears — recorded `computations 0`, `paths []`,
  `replacement NONE`, and the RLS dataset probe shows the hidden concept absent for the operator. The recorded runtime flag
  is `leaks_hidden_id=true` / `LEAK_OR_UNEXPECTED`; that detector was a plain substring that also matches
  `metrics/gross-margin-legacy` (the forced seed), and the full answer payload was not retained, so the *no-hidden-identifier*
  claim is **INCONCLUSIVE** — path removal is corroborated, absence of any hidden identifier is not verified. The
  detector is now exact and full payloads are persisted (`run.py`), but no re-run was made (no new spend).
* **Natural question on the RLS dataset:** same INCONCLUSIVE label for the same reason; circumstantially the legacy seed
  reached no computation (it reaches one at two hops without RLS).
* **Impact on the RLS dataset:** recorded flag false; the hidden concept is absent from the impacted set — ENFORCED.
* **Metadata visible, Section rows denied:** the reachable computation is returned with `sql = null` and an explicit
  `SOURCE_DENIED_OR_MISSING` warning — WITHHELD.
* **Revoke before cached replay (all rows → FILTER USING (FALSE)):** cached replay re-check fails closed (`HIT_DENIED`).
  Edge-only revocation was **not** exercised live. The first fix still dropped traversal `edge_ids` at the outer SQL
  projection, allowing a revoked second-hop edge to survive replay. The outer SELECT now returns those IDs; version-2
  cache entries require complete traversal/context edge dependencies, intermediate nodes and seed sections. Incomplete
  or legacy cache entries trigger fresh retrieval. Offline regressions in `tests/test_cache.py` cover second-hop
  revocation using actual result columns; this is a code fix, not a new measurement.
* **Authorized views:** `CREATE PROPERTY GRAPH` accepts views as node/edge tables and GQL runs over them — graph-input
  acceptance: ACCEPTED (same operator identity; no second principal). Disclosure: **INCONCLUSIVE**, because the recorded
  leak flag is true and the full payload was not retained. Acceptance of views does not establish absence of hidden IDs.

Time-based side channels were not tested. The governance table shows the recorded verdicts unmodified alongside the
post-hoc note; the renderer does not mutate any recorded verdict. For future retained payloads, an exact positive hidden-ID
check publishes **FAIL/LEAK**, including when the recorded runtime flag disagrees; graph-input acceptance stays separate.

## G7 — atomic publication, revocation, cached replay (PARTIAL)

Failed publish (injected failure before the pointer switch) raises and leaves the old pointer — PASS, read back live.
Concurrent `active`-pointer requests during the re-publish of `bundle_b` all reported the old pin by `scope.publication_id`,
but the checker used at measurement time compared only that scope field (it tried to parse publication ids out of SQL
digests, which never contain one) and could not have detected a mixed payload — **PARTIAL**. The checker is replaced by
`single_pin()` now checks scoped identifiers including provenance `source_id`, and hashes returned SQL bytes against
independently pinned expected digests. Its guarantee explicitly excludes unscoped paths, section headings/text and
provenance attributes; those fields do not establish content integrity. Negative offline tests cover substituted SQL
and foreign provenance (`tests/test_governance_checks.py`); the live case was not re-run, and G7 remains PARTIAL.
Old versions are retained (append-only tables).

## G8 — benchmark and cost (INCOMPLETE)

**0 of 9 benchmark cells completed.** `acme_c1` (GQL, C=1, uncached) reached 20 warmups + **28 of 100** measured requests
(00:22:31→00:26:27Z) before the driver was interrupted for cost control; C=5, C=10 and both synthetic scale corpora
(`copies_100`, `copies_1000`, published but never queried under the benchmark) are **NOT_RUN_BUDGET**. The per-cell table
above is generated from `summary.json` (`partial.py` refreshes unfinished rows from raw `requests.jsonl`, separated by
`run_id`; the retained run is `legacy-unlabeled`). All nine combinations include their corpus, concurrency and target;
the eight unrun cells include `x100_c10`, with zero measured requests and null percentiles. The INCOMPLETE row's
nearest-rank p50/p95 over 28 attempts are shown with that sample size and are **not** a completed cell. No concurrency or
scale SLO result exists; the proposed p95-at-C=5 target is therefore **NOT_RUN**, and any statement about it below is a
hypothesis.

Individual integration-run latencies (each n=1, uncached, C=1, from `all_all-0017.json`): forced seeds 4.40 / 3.95 / 5.43 s;
natural questions 5.47 / 5.71 s after batching the walk (18.22 s in `all_all-0012.json` when one walk job ran per seed);
impact 4.39 s (3.46 s in `all-0012`). Relational fallback on-demand: **natural** question 5.67 s (n=1,
`natural_question_fallback.json`, includes query embedding + vector seed); **forced** seed 2.61 s and 2.13 s (n=2,
`landmine_forced_fallback.json`, `all-0017`). Forced and natural shapes are not comparable to each other.

Cost (`cost.json`, span 23:40→00:35Z, provisional until the billing export reconciles): the named Enterprise reservation
ran 323 jobs for 1,988,844 slot-ms → attribution **$0.033**; 26 jobs (86,674 slot-ms) landed on `default-pipeline` and are
reported separately; on-demand jobs billed 1.29 GB → $0.0074 at list rate (free tier not applied, so likely $0.00 invoiced).
The capacity bill uses the platform's charged quantity, `period_autoscale_slot_seconds` from
`INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`: **21,750 slot-seconds → $0.36** across all windows (timeline coverage through
00:27, matching the last DELETE at 00:27:27Z; the earlier "$0.25 from 250 snapshot slot-minutes" was a snapshot sum, not the
charged quantity). Storage, embeddings (22 + 6 + 2×7 sections plus query embeddings) and publication upkeep were **not
quantified** (NOT_MEASURED); the 10,000-requests/day utilization model was **not built** (NOT_MODELED). The decision-relevant
observation stands: a zero-baseline reservation charges 50 slots for at least a minute whenever any GQL job runs, so sparse,
bursty analytical-agent traffic pays about $0.05 per active minute regardless of how little work each query does.

## G9 — comparison and envelope decision

`comparison.md` carries the four-way table with evidence labels. Against the proposed (unaccepted) envelope of p95 ≤ 5 s at
C=5, ≥99% success, ≤60 s publication visibility and ≤$0.05 amortized per request at 10k/day: publication visibility was
21.3 s for the one Acme publish (n=1, not a distribution); p95 at C=5 is **NOT_RUN** — the *hypothesis* from 28 C=1 samples
(p50 4.4 s, p95 5.4 s) is that it would not meet 5 s without a warm baseline or a different serving layer; the 10k/day cost
model is NOT_MODELED (`OPERATING_ENVELOPE_UNACCEPTED` — no customer acceptance was recorded). Neo4j is RECORDED semantics
only; Spanner Graph is DOCUMENTED/NOT_RUN; KC + ordinary SQL/vector reproduces the same forced two-hop context on-demand in
2.1–2.6 s (n=2) and the natural question in 5.7 s (n=1) with no reservation, with fixture-driven discovery (no live KC call)
and without GQL impact analysis — no matched concurrency or cost-per-success comparison exists.

## Outcome and joint-decision inputs

* **GQL passed** for the demonstrated retrieval slice (G1–G5); G6 and G7 are PARTIAL; G8 is INCOMPLETE (0/9 cells).
  Capacity was not blocked; semantics did not fail in the measured cases. Per JOINT §4 this supports **MODERATE delivery for
  graph retrieval only**, with the operating-envelope half of the question (p50/p95 at concurrency and scale) explicitly
  NOT_RUN; combined delivery remains **LOW** (no connected KC discovery → publication → walk → caller computation →
  result-bound receipt path was run).
* Downgrade-trigger watch: Enterprise economics for bursty per-request retrieval (one-minute 50-slot minimum per burst) and
  job-overhead-bound latency both point toward "ordinary KC/SQL retrieval or an online engine plus BigQuery execution" unless
  a customer accepts a warm baseline; this must be revisited at the 2026-09-19 checkpoint with the completed cells.
* BLOCKED / INCONCLUSIVE / NOT_RUN list: distinct-principal authorization negatives (classifier denial); no-hidden-identifier
  claim for the RLS/authorized-view cases (detector defect, payload not retained); mixed-payload single-pin claim (checker
  defect); edge-only cached revocation (not exercised live); benchmark concurrency/scale cells; Neo4j/Spanner matched runs;
  live KC seed; storage/embedding/upkeep cost and the 10k/day model.

## Teardown status

Every reservation CREATE has a matching platform DELETE (`reservation_changes.json`; last DELETE 00:27:27Z; cumulative
lifetime 18.7 min). Two windows were closed outside the driver (`integration-0009` by the safety watcher, `all-0017` after a
SIGINT) and are reconstructed in `cleanup_manifest.json` from the platform record. `reservation.py` now reports
DELETE_UNVERIFIED unless every delete succeeded and a successful listing shows nothing left; a verified retry clears that
outstanding state and stamps the verified deletion time. The window job gate stops readiness, integration, publication and
benchmark submissions before canceling journaled job IDs and tearing down capacity. `bin/safety_teardown.sh` independently
cancels those jobs and retries strict cleanup for the original window label; failed inventory remains unverified. These
paths are covered offline and were not exercised in a new live window. Temporary datasets
`okf_graph_spike_20260905{,_x100,_x1000,_rls,_meta,_av}` and their remote embedding models carry a 14-day default table
expiration (dataset objects themselves are not auto-deleted); they retain the governed evidence and can be dropped earlier
by the operator. No shared assignment or resource outside this spike was touched.

## Addendum 2026-09-06: connected chain (fixture seed, same requester)

`okf_bq_graph/chain.py` ran the path this report's outcome section called missing, with two honest narrowings: the seed is
the harness fixture (no KC discovery) and both legs run under the operator's own credential. Fixture seed → pinned
publication `pub_190192147fd7fd78` → governed retrieval returns the Attested Computation declaration and SQL for
`computations/gross-margin-period.md` (`NOT_EXECUTED`) → bind to the SDK receipt example's pinned publication by data files
(file SHA-256 `5e96ae11…`, SQL text, parameters, source pin `31da799`) → SDK CLI at `6719eb5` as a subprocess executes and
independently verifies → consumer releases only on VERIFIED with the receipt's `computation_digest` recomputed from the bound
bytes. Hermetic (oracle graph engine + SDK SYNTHETIC emulation): **CHAIN_CONNECTED** — `approved` RELEASED, the SDK's
`sql-substitution` REFUSED (`REJECTED sql_mismatch`, no number), `declaration-mismatch` (revenue-ytd offered instead) REFUSED
before any execution (`evidence/chain/chain_hermetic.json`). Live (relational fallback engine, on-demand, not BigQuery
Graph; SDK `--live`, 2026-09-06 21:35Z, one foreground pass, `evidence/chain/chain_live.json`): **CHAIN_CONNECTED** — pointer
= pin, one-hop reach in 2.4 s (three on-demand jobs + one declaration job), all ten bind checks hold, receipt job
`okf_rcpt_b30edb60…` VERIFIED / MATCH under the operator's credential, consumer RELEASED `$400.00 USD` on the SDK's synthetic
fixture dataset, both substitutions REFUSED, `same_requester = SAME` (`jobs.get user_email` identical on the graph jobs and
the receipt job), 21 s end to end. This is the connected **publication → retrieval → execution → receipt → consumer** path
under one requester on the relational engine; it is not connected KC discovery (fixture seed), not the GQL engine, and not
a second principal, so the combined-delivery verdict in the outcome section is for the JOINT checkpoint to revise, not this
addendum.
