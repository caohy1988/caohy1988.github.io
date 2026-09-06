# Summary — BigQuery Graph spike (2026-09-05/06)

| Gate | Outcome | Evidence |
|---|---|---|
| G1 capacity | **PASSED (measured)** — no reservations anywhere; on-demand GQL rejected with the edition error; Enterprise pay-as-you-go autoscaling reservation (0 baseline, ≤100) created, GQL smoke job on it (edition ENTERPRISE, 21,410 slot-ms), torn down and verified. Assignment propagation ≈2 min and non-atomic. | `capacity-gate.md`, `capacity.json`, `smoke_*`, `cleanup_manifest.json` |
| G2 projection | **PASSED** — deterministic, scoped, closed; 44 nodes / 109 edges / 22 sections; unknown frontmatter preserved; negatives fixture behaves as specified | `projection_acme.json`, `tests/` |
| G3 landmine | **PASSED** — deprecated anchor → current metric → sanctioned SQL in 2 hops in GQL; all fields match oracle; natural question seeds current + policy + deprecated side by side | `all_all-0017.json`, `report.md` |
| G4 impact / backlog | **PASSED** — GQL `ACYCLIC {1,6}` impact set and min hops equal oracle; stub backlog equal oracle (Acme empty, bundle_b 3 stubs) | `all_all-0017.json` |
| G5 duplicates / scope / ambiguity / stale | **PASSED** | `all_all-0017.json`, `tests/` |
| G6 authorization | **PARTIAL** — RLS honoured inside GQL walk; SQL withheld when Section rows denied; revoke-before-cached-replay fails closed; graph over authorized views accepted. **BLOCKED**: every case needing a distinct real principal (SA creation denied by session classifier). | `authz_setup.json`, `all_all-0017.json` |
| G7 publication | **PASSED** — concurrent requests during re-publish each single-pinned; failed publish leaves old pointer | `all_all-0017.json`, `publish_log.jsonl` |
| G8 benchmark / cost | **see `summary.json`** — only cells marked COMPLETE carry p50/p95; others NOT_RUN/INCOMPLETE. Single requests: 3.9–5.7 s uncached (2–4 sequential jobs). Capacity bill so far ≈ $0.25 (5 × 50-slot minutes), slot attribution $0.011, on-demand $0.007 — provisional. | `summary.json`, `requests.jsonl`, `cost.json` |
| G9 comparison | Neo4j RECORDED, Spanner DOCUMENTED/NOT_RUN, KC+SQL fallback MEASURED on-demand (~2 s, no GQL impact), BQ Graph MEASURED. Envelope **UNACCEPTED**. | `comparison.md` |

**Delivery input for the joint checkpoint:** MODERATE for the graph-retrieval slice only; combined delivery stays LOW
(no connected receipt path). Watch downgrade triggers: per-burst one-minute 50-slot minimum and job-overhead-bound latency.
