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
