# OKF `acme_retail` → BigQuery Graph spike (2026-09-05)

**Question.** Can BigQuery Graph (GA GQL, Enterprise capacity) preserve the useful semantics of Acme's OKF graph and perform
seed-plus-two-hop governed retrieval within an analytical agent's operating envelope, at an honest Enterprise cost?
Plans: intent / spec / plan in `/tmp/okf-spikes/graph/` (vault copies `Ship/rfc/2026-09-05-spike-graph-*.md`).
Joint framing: `JOINT_final.md` (parallel-spike, receipts-gated). **Results: [`evidence/report.md`](./evidence/report.md).**

This is an experimental module, not a production serving-tier commitment. It does not implement or substitute for a
result-bound receipt; the sanctioned SQL it returns is retrieval evidence only (`runtime_verdict = NOT_EXECUTED`).

## What is here

| Path | Purpose |
|---|---|
| `okf_bq_graph/capacity.py` | Task 1 read-only capacity inventory (reservations, assignments, ancestry, IAM, public SKUs) → `evidence/capacity.json` |
| `okf_bq_graph/reservation.py` | Execution-only Enterprise window open/close with cleanup manifest (`evidence/cleanup_manifest.json`) |
| `okf_bq_graph/model.py`, `compile.py` | Deterministic OKF v0.2 → scoped node/edge projection (no LLM, never executes bundle code, strict path resolution, unknown frontmatter preserved) |
| `okf_bq_graph/oracle.py` | Relational/Python reference: governed context, impact (≤6 edges, simple paths), stub backlog; pinned expectations |
| `okf_bq_graph/publish.py` | Immutable publication: append → readback validation (counts, dangling, vector digests) → `READY` → atomic pointer `MERGE`; failure injection before pointer |
| `okf_bq_graph/retrieve.py` | `retrieve / impact / stub_backlog` with engines `gql` (GA `VECTOR_SEARCH` seed + GQL walk), `fallback` (relational joins, on-demand), `oracle`; cache with re-check at disclosure; fail-closed |
| `okf_bq_graph/scale.py` | Synthetic 100 / 1,000 namespace-isolated copies in their own datasets (vectors reused by text digest) |
| `okf_bq_graph/authz.py` | Governance fixtures: RLS dataset (hidden intermediate), metadata-only dataset, authorized views + graph over views |
| `okf_bq_graph/benchmark.py`, `run.py` | Bounded runner (20 warmups + 100 measured per cell, nearest-rank percentiles, failures retained) and the window orchestrator with watchdog |
| `okf_bq_graph/cost.py` | Slot attribution vs allocated-capacity bill from `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` |
| `sql/*.sql` | `schema.sql`, `graph.sql` (property graph DDL), `seed.sql` (vector seed), `governed.sql` (two-hop GQL), `context.sql`, `impact.sql`, `stubs.sql`, `fallback.sql` |
| `fixtures/bundle_b/` | Negative fixture: identical relative paths, missing targets, duplicate hits, ambiguous replacement, `../` escape |
| `fixtures/cases.json`, `fixtures/scale.json` | Query set and benchmark cell matrix |
| `tests/` | `test_compile.py`, `test_oracle.py`, `test_retrieve.py` (contract runs against oracle by default; `OKF_LIVE_ENGINE=gql|fallback` runs it live) |
| `evidence/` | Raw captures: capacity gate, smoke jobs, projection, publish log, integration/governance JSON, `requests.jsonl`, `summary.json`, `cost.json`, comparison, report |

Source pin: `/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail` @ knowledge-catalog `31da799a9aef176df12e91abbd119ea9385b75ec`
(17 markdown files + 2 artifacts; per-file SHA-256 in `evidence/projection_acme.json`). Publication id
`pub_190192147fd7fd78` is derived from the source manifest digest, not from PR 474's observation publication.

## Graph model (spec §3)

Node kinds `Concept | Section | Source | Actor | Artifact | LogEntry`; stubs are `Concept{stub=true}`. Relations
`LINKS_TO, HAS_SECTION, NEXT, CITES, MENTIONS, DERIVES_FROM, RESOLVES_TO, GENERATED_BY, VERIFIED_BY, EXECUTED_BY, ATTESTED_BY, REFERENCES`.
`node_id = bundle|publication|kind|local`; `edge_id = bundle|publication|relation|sha256(endpoints, declaration, ordinal)`.
One property graph `okf_graph` with uniform `Node`/`Edge` labels; every query carries `publication_id` predicates.
Acme compiles to 44 nodes / 109 edges / 22 sections, 0 stubs; `bundle_b` to 17 / 28 / 6 with 3 stubs.

## Run

```bash
python3 -m pytest tests -q                                   # 16 tests, oracle engine
python3 -m okf_bq_graph.capacity US us-central1 EU           # read-only inventory
python3 -m okf_bq_graph.compile <bundle_root> evidence/projection_acme.json
python3 -m okf_bq_graph.publish <bundle_root>                # on-demand: tables, vectors, graph DDL, pointer
OKF_LIVE_ENGINE=fallback python3 -m pytest tests/test_retrieve.py -q   # live, on-demand
python3 -m okf_bq_graph.run integration|benchmark|all --minutes N       # opens/closes the Enterprise window
python3 -m okf_bq_graph.cost <since> <until>                 # reconcile jobs + reservation timeline
```

Everything cloud-side lives in `okf_graph_spike_20260905{,_x100,_x1000,_rls,_meta,_av}` (US, 14-day default expiration)
and in the temporary reservation `okf-graph-spike-20260905` (Enterprise, 0 baseline, autoscale ≤100, no idle borrowing),
which is created only inside a measured window and deleted at its end (`evidence/cleanup_manifest.json`).
