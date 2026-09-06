# Four-way placement comparison (G9) — evidence labels: MEASURED · RECORDED · DOCUMENTED · NOT_RUN · BLOCKED

Same pinned corpus (`acme_retail` @ knowledge-catalog `31da799`), same question set (`fixtures/cases.json`), same
semantics (spec §4). Numbers appear only where this spike measured them; see `summary.json` and `report.md`.

| Alternative | Retrieval semantics | Latency / cost | Governance inside traversal | Evidence label |
|---|---|---|---|---|
| **BigQuery Graph (GA GQL on Enterprise)** | Vector seed (GA `VECTOR_SEARCH`) → GQL `LINKS_TO{1,2}` walk → context assembly; impact via `MATCH p = ACYCLIC … {1,6}`; stub backlog | single requests only: forced 3.9–5.4 s, natural 5.5–5.7 s (n=1 each); `acme_c1` INCOMPLETE 28/100 (p50 4.4 s / p95 5.4 s); C=5/C=10/scale cells NOT_RUN; capacity bill $0.36 charged autoscale slot-seconds across all windows | RLS removes the hidden path inside the GQL walk (path removal corroborated; no-hidden-id claim INCONCLUSIVE); authorized views ACCEPTED as graph inputs (filtered view, same identity); distinct-principal cases BLOCKED | MEASURED (retrieval, impact, backlog, capacity cost); INCOMPLETE (benchmark); BLOCKED (second principal) |
| **KC + ordinary SQL/vector (on-demand)** | Same seed; relational two-hop joins (`sql/fallback.sql`); impact needs recursive SQL (NOT_RUN here) | forced seed 2.61 s / 2.13 s (n=2); natural question 5.67 s (n=1, includes embedding + vector seed) — shapes not comparable to each other; on-demand list-rate bytes | ordinary RLS/authorized views apply to plain SQL (platform-documented, not separately measured here) | MEASURED (fallback retrieval, single requests); fixture-driven discovery — no live KC endpoint was called, so **connected KC evidence is unproven** |
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
