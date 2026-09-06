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
