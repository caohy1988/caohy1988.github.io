# Spec — September 19 2026 decision pack (Slice A)

Files: `rfc/board-pack/{index.html,STORY.md,intent-sep19-pack.md,spec-sep19-pack.md,plan-sep19-pack.md}`; `rfc/spikes/bq-graph/{README.md,fixtures/sql_baseline.json,okf_bq_graph/sql_baseline.py,tests/test_sql_baseline.py,evidence/sql-baseline/*}`. `rfc/index.html` is untouched in this slice.

## 1. Evaluation card — visible, deep-linkable, every threshold PROPOSED

New `<section class="runtime-rule" id="sep19-envelope">` between the Enterprise-capacity rule and the Technical design frame, using the existing `#later-questions` markup pattern so no CSS changes. Mirrored in `STORY.md` as a table.

| Field | Recorded value | Label |
|---|---|---|
| Owner | Haiyuan Cao (`caohy1988`) | NAMED 2026-09-07; has accepted no threshold |
| Task | An analyst's agent retrieves a pinned definition, the rules it links to and the declared calculation, and releases a number only when a receipt bound to that calculation verifies | PROPOSED |
| Corpus and fact versions | `acme_retail`, publication `pub_190192147fd7fd78`, source pin `31da799a`, 17 documents + 2 artifacts, question set at `as_of` 2026-09-05 | FIXED — what every experiment used |
| Concurrency | C=5; C=1 is the only concurrency any recorded observation covers | PROPOSED, planning default |
| Request volume | 10,000 requests/day | PROPOSED, model never built |
| Tolerated latency | Retrieval p95 ≤ 5 s at C=5, reported separately from full request-to-consumer time; no threshold proposed for the latter because nothing has sampled it | PROPOSED |
| Freshness | Republished definition visible to new requests ≤ 60 s (one publish: 21.3 s, n=1); an in-flight request keeps its pinned publication by design | PROPOSED |
| Retention | 15 months of context, access and receipt records | PROPOSED, no measurement behind the horizon |
| Success definition | ≥99% of requests release a verifying-receipt number or refuse with a stated reason; zero releases without a verifying receipt; zero disclosures of denied content | PROPOSED |
| Total-cost ceiling | ≤ $0.05 per answered question at 10,000/day, including failed and refused attempts, embeddings, storage, publication upkeep and any reserved capacity | PROPOSED, nothing measured against it |
| Decision rule | Continue / narrow / stop against accepted thresholds; if ordinary SQL meets the need, GQL must justify its extra cost; if nobody accepts the envelope, narrow the scoped opportunity | — |

Acceptance: the card names Haiyuan Cao as owner and states he has accepted nothing; the words "no Finance or data owner outside this project has been asked" appear; the historical 5.4 s is described as a partial sample from 28 of 100 attempts at C=1, not an agreement; "more demonstration evidence is not pilot validation" appears in the decision rule.

## 2. Bounded ordinary-SQL baseline scaffold

`fixtures/sql_baseline.json` predeclares, and `okf_bq_graph/sql_baseline.py` renders, `evidence/sql-baseline/{plan.json,baseline.md}` offline.

- Engine `fallback` (relational two-hop joins plus the GA vector seed for natural questions), same pinned corpus, same question set, same `as_of`.
- Four retrieval cells: forced and natural shapes at C=1 and C=5, 20 warmups + 100 measured each, 60 s timeout, result cache off. Shapes are never pooled.
- Two request-to-consumer cells at C=1 and C=5, 2 warmups + 20 measured. `NOT_IMPLEMENTED`: no sampled runner exists.
- `retrieval_ms` and `request_to_consumer_ms` are separate cells and are never substituted. The 2026-09-06 23-second three-case chain pass is neither metric, and the card says so.
- Five cost cells listed rather than omitted, all `UNMEASURED`: publication visibility, publication upkeep, embedding, storage, and cost per success with failed and refused attempts in the numerator and out of the denominator.
- Budget: 900 s per cell, 3600 s total, 64 GiB billed, $0.50 on-demand at list, no reservation, with a stop rule that retains attempts. The card projects the declared samples from observed bytes per request (37.5 GiB → $0.23) and reports whether that fits.
- Three recorded prior SQL observations are read out of the retained evidence and carried beside the cells with `fills_cell: false`.

Acceptance: every cell `INCOMPLETE`, every cost cell `UNMEASURED`, no prior observation filling a cell, and the committed artifacts byte-identical to their generator.

## 3. One correction the scaffold carries

`evidence/report.md` and `evidence/comparison.md` describe both forced fallback observations as on-demand. Every job in `all_all-0017.json#fallback_forced` carries the spike's Enterprise reservation. The scaffold reads the edition from the jobs in each record and states the discrepancy; the dated records are left as they are.

## 4. PR 45 honesty — three stale sentences

PR 45 (`ad18b07`) ran retrieval and the receipt check under `sa:okf-receipt-restricted` live: `CHAIN_CONNECTED`, four acceptances `MET`, 29 submitted jobs matched to the role that submitted them (20 requester, 9 operator administrative), reconciled against a drained job listing, teardown `VERIFIED`. Three page sentences predate it.

- Closed skim: "what we still need to prove: the same chain … for a second identity and a policy decision" → one chain that does catalog discovery, a restricted identity and graph queries **at once**, on real cohort data.
- Access section: "Work since then on a deliberately restricted requester exists only as offline tests" → it has now run live, naming the three refusals inside that chain, the hand-chosen seed, plain SQL and the same invented data.
- Evidence bar: "the separate-identity checks cover the other three tests, each in isolation and outside any chain" → five in isolation on 6 September, plus the 7 September restricted chain; **no single chain has yet done both** a live catalog read and a second identity.

Not claimed: a catalog read on the restricted chain, graph queries, an independent attester, real cohort data, or any score movement.
