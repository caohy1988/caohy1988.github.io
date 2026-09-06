# Four-way placement comparison (G9) — evidence labels: MEASURED · RECORDED · DOCUMENTED · NOT_RUN · BLOCKED

Same pinned corpus (`acme_retail` @ knowledge-catalog `31da799`), same question set (`fixtures/cases.json`), same
semantics (spec §4). Numbers appear only where this spike measured them; see `summary.json` and `report.md`.

| Alternative | Retrieval semantics | Latency / cost | Governance inside traversal | Evidence label |
|---|---|---|---|---|
| **BigQuery Graph (GA GQL on Enterprise)** | Vector seed (GA `VECTOR_SEARCH`) → GQL `LINKS_TO{1,2}` walk → context assembly; impact via `MATCH p = ACYCLIC … {1,6}`; stub backlog | single requests only: forced 3.9–5.4 s, natural 5.5–5.7 s (n=1 each); `acme_c1` INCOMPLETE 28/100 (p50 4.4 s / p95 5.4 s); 0/9 cells complete; eight remaining cells NOT_RUN_BUDGET; capacity bill $0.36 charged autoscale slot-seconds across all windows | RLS removes the hidden path inside the GQL walk (path removal corroborated; no-hidden-id claim INCONCLUSIVE); authorized views ACCEPTED as graph inputs (same identity), disclosure INCONCLUSIVE; **distinct principal (2026-09-06, `sa:okf-receipt-restricted` via impersonation, relational fallback engine on the same RLS tables): 5/5 MEASURED behind a working allowed control** (same SA, same restricted fixture: allowed seed OK with 1 computation, negative seed visible) — hidden intermediate ENFORCED (0 paths, 0 computations, exact-match hidden id absent), denied bundle DENIED with 0 identifiers in response or API error, output denied with the seed store visible (19 vector rows by row count under the SA, 0 node/edge rows, 0 foreign ids; natural-language seed DENIED under the SA and folded into the verdict), owner-fallback NO_FALLBACK (3/3 SA jobs `user_email` = SA, 3/3 owner jobs = operator; the owner arm runs on the ungoverned base dataset, and the owner on the governed fixture also sees no hidden path), revocation before cached replay FAIL_CLOSED on every surface (`HIT_DENIED`, 0 content, 0 ids, 11 s after the dataset grant was removed) plus an owner-stored entry replayed under the SA DENIED (cache bound to the credential, not the label); teardown VERIFIED step by step; every publication identifier masked in the evidence; **the same five cases inside a GQL traversal remain BLOCKED** (needs the bounded window lifecycle for both clients; window gate also refuses on an unverified legacy job journal) — `authz_cases.json` | MEASURED (retrieval, impact, backlog, capacity cost; second principal on relational fallback); INCOMPLETE (benchmark); BLOCKED (second principal inside GQL) |
| **KC + ordinary SQL/vector (on-demand)** | Same seed; relational two-hop joins (`sql/fallback.sql`); impact needs recursive SQL (NOT_RUN here) | forced seed 2.61 s / 2.13 s (n=2); natural question 5.67 s (n=1, includes embedding + vector seed) — shapes not comparable to each other; on-demand list-rate bytes | ordinary RLS/authorized views apply to plain SQL (platform-documented, not separately measured here) | MEASURED (fallback retrieval, single requests); fixture-driven discovery — no live KC endpoint was called, so **connected KC evidence is unproven**; a fixture-seeded graph → receipt chain on this engine is recorded under `chain/` (see "Connected chain" below) |
| **Neo4j (Lyon, johnymontana/neo4j-okf @ d0641b9)** | Recorded governed retrieval, impact, backlog queries (`okf_graph/queries.py`); replacement = first stable same-type link by id (this spike instead returns AMBIGUOUS when >1) | no numbers recorded by the article; no local matched run in this session (Neo4j not installed) | policy enforcement not part of the recording | RECORDED (semantics), NOT_RUN (latency) |
| **Spanner Graph** | Same GQL dialect family; Google positions it for online small-neighbourhood retrieval ([graph-compare](https://docs.cloud.google.com/bigquery/docs/graph-compare)) | no authorized existing instance; no new paid instance created | fine-grained access control documented, not measured | DOCUMENTED, NOT_RUN |

## Notes on the Neo4j reference

* Lyon's repo bundle differs from the pinned KC bundle: `stale_after`/`last_modified` were rewritten to date-only
  values (e.g. `2026-12-31` vs `2026-12-31T00:00:00Z`) in eight files. This spike compiles the **KC-pinned** bytes
  and keeps the authored timestamp text; freshness is evaluated at an explicit `as_of` instant (spec §4).
* Lyon's `GOVERNED_RETRIEVAL_QUERY` picks `collect(cand)[0]` ordered by id as the replacement; spec §4 forbids
  silently picking one, so `bundle_b` (two stable candidates) yields `AMBIGUOUS` here and no executable replacement.
* Lyon's parser resolves bare root-relative paths as a fallback; this compiler does the same but labels such edges
  `root_fallback` / `inferred=true` (Acme's `executor`/`attester` fields need it).
* Impact relation set and 1..6 bound are identical; Lyon's Cypher does not exclude cycles explicitly (Neo4j
  variable-length patterns are relationship-unique), this spike uses `ACYCLIC` in GQL and simple paths in the oracle.

## Connected chain (2026-09-06, `chain/`)

`okf_bq_graph/chain.py` runs fixture seed → pinned publication → governed retrieval (declaration + SQL, NOT_EXECUTED) →
bind to the SDK receipt example's pinned publication (file SHA-256, SQL text, parameters, source pin) → SDK CLI at
`6719eb5` as a subprocess (caller-delegated execution + independent verifier) → consumer. Same requester on both legs
(operator ADC; the restricted SA is not exercised). Hermetic (oracle graph + SDK SYNTHETIC emulation): `CHAIN_CONNECTED`,
`approved` RELEASED, `sql-substitution` REFUSED (`REJECTED sql_mismatch`), `declaration-mismatch` REFUSED before any
execution (`chain_hermetic.json`). Live (relational fallback engine, on-demand, not BigQuery Graph; SDK `--live` real jobs
on the synthetic fixture dataset, 2026-09-06 21:35Z, one foreground pass, `chain_live.json`): `CHAIN_CONNECTED` — the same
three decisions, `same_requester = SAME` by `jobs.get user_email` on the three graph jobs and the receipt job, 21 s end to end. The seed is a fixture: this is a connected
**publication → retrieval → execution → receipt → consumer** path, not connected KC discovery, which stays unproven.
