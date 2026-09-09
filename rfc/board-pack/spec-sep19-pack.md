# Spec — September 19 2026 decision pack (Slice A)

Files: `rfc/board-pack/{index.html,STORY.md,intent-sep19-pack.md,spec-sep19-pack.md,plan-sep19-pack.md}`; `rfc/spikes/bq-graph/{README.md,fixtures/sql_baseline.json,okf_bq_graph/sql_baseline.py,tests/test_sql_baseline.py,evidence/sql-baseline/*}`. `rfc/index.html` is untouched in this slice.

## 1. Evaluation card — visible, deep-linkable, every threshold PROPOSED

New `<section class="runtime-rule" id="sep19-envelope">` between the Enterprise-capacity rule and the Technical design frame, using the existing `#later-questions` markup pattern so no CSS changes. Mirrored in `STORY.md` as a table.

| Field | Recorded value | Label |
|---|---|---|
| Owner | Haiyuan Cao (`caohy1988`) | NAMED 2026-09-07; has accepted no threshold |
| Task | An analyst's agent retrieves a pinned definition, the rules it links to and the declared calculation, and releases a number only when a receipt bound to that calculation verifies | PROPOSED |
| Corpus and definition versions | `acme_retail`, publication `pub_190192147fd7fd78`, source pin `31da799a`, 17 documents + 2 artifacts, question set at `as_of` 2026-09-05. Fixes the authored definitions and the graph projection; identifies no fact data | FIXED — what every experiment retrieved from |
| Fact data and its version (comparison fixture) | The receipt example's synthetic Acme fixture: 7 tables, 14 rows in `test-project-0728-467323.okf_receipt_spike_20260905` (`fulfillment_cost`, `fx_daily_rates`, `order_lines`, `orders`, `payment_fees`, `products`, `shipment_cost`), reached through the receipt example's own publication `okf-receipt-spike/acme-retail-derived/gross-margin-period` at SDK pin `6719eb5`, a separate identity from the graph publication joined to it only by the declaration file's bytes. Pinned by the digest of the script that loads them (`940aacdc…`) and a canonical content manifest (`7264e7df…`), vendored under `fixtures/facts/`; loaded 2026-09-05, expiring about 2026-10-05; live rows unverified against the digest and the September 7 chain's equivalence unproven; a run must pass the recorded live precheck first. Invented data chosen so the measurement can be repeated (`spec-sqlchain-fact-select.md`) | **SELECTED (synthetic)** 2026-09-09 — clears `FACTS_UNSELECTED` only; `sqlchain_forced_c1` / `sqlchain_forced_c5` stay `RUNNER_HERMETIC_ONLY` (`NOT_IMPLEMENTED` until the hermetic-only runner landed) |
| Customer fact data (Alder cohort) | Never selected. A customer's to give, not ours to invent; no Finance or data owner outside this project has been asked | **NOT SELECTED** — customer dependency |
| Concurrency | C=5; C=1 is the only concurrency any recorded observation covers | PROPOSED, planning default |
| Request volume | 10,000 requests/day | PROPOSED, model never built |
| Tolerated latency | Retrieval p95 ≤ 5 s at C=5, reported separately from full request-to-consumer time; no threshold proposed for the latter because nothing has sampled it | PROPOSED |
| Freshness | Republished definition visible to new requests ≤ 60 s (one publish: 21.3 s, n=1); an in-flight request keeps its pinned publication by design | PROPOSED |
| Retention | 15 months of context, access and receipt records | PROPOSED, no measurement behind the horizon |
| Success definition | ≥99% of requests release a verifying-receipt number or refuse with a stated reason; zero releases without a verifying receipt; zero disclosures of denied content | PROPOSED |
| Total-cost ceiling | ≤ $0.05 per answered question at 10,000/day, including failed and refused attempts, embeddings, storage, publication upkeep and any reserved capacity | PROPOSED, nothing measured against it |
| Decision rule | Continue / narrow / stop against accepted thresholds; if ordinary SQL meets the need, GQL must justify its extra cost; if nobody accepts the envelope, narrow the scoped opportunity | — |

Acceptance: the fact-version field is present rather than being folded into the corpus pin (it read UNSELECTED until 2026-09-09 and now reads SELECTED (synthetic) with the customer cohort as its own NOT SELECTED row), and the corpus row no longer claims to be "what every experiment used" without qualification; the card names Haiyuan Cao as owner and states he has accepted nothing; the words "no Finance or data owner outside this project has been asked" appear; the historical 5.4 s is described as a partial sample from 28 of 100 attempts at C=1, not an agreement; "more demonstration evidence is not pilot validation" appears in the decision rule.

## 2. Bounded ordinary-SQL baseline scaffold

`fixtures/sql_baseline.json` predeclares, and `okf_bq_graph/sql_baseline.py` renders, `evidence/sql-baseline/{plan.json,baseline.md}` offline.

- Engine `fallback` (relational two-hop joins plus the GA vector seed for natural questions), same pinned corpus, same question set, same `as_of`.
- Four retrieval cells: forced and natural shapes at C=1 and C=5, 20 warmups + 100 measured each, 60 s timeout, result cache off. Shapes are never pooled.
- Two request-to-consumer cells at C=1 and C=5, 2 warmups + 20 measured. `RUNNER_HERMETIC_ONLY` since 2026-09-09 (`NOT_IMPLEMENTED` before): the sampled runner has dry-run and hermetic modes only, so no live attempt has been sampled and nothing fills them.
- `retrieval_ms` and `request_to_consumer_ms` are separate cells and are never substituted. The 2026-09-06 23-second three-case chain pass is neither metric, and the card says so.
- Five cost cells listed rather than omitted, all `UNMEASURED`: publication visibility, publication upkeep, embedding, storage, and cost per success. The last one states one formula in one place — **total cost of all attempts ÷ released, receipt-verified answers** — because a failed or refused attempt costs money (numerator) and answered nothing (not the denominator). `validate_plan` refuses a `cost_per_success` spec with no formula.
- Budget: 900 s per cell, 3600 s total, 64 GiB billed, $0.50 on-demand at list, no reservation, with a stop rule that retains attempts. The card projects the declared samples from observed bytes per request (37.5 GiB → $0.23) and reports whether that fits.
- A `facts` block records the fact-data version. Until 2026-09-09 it was `state: UNSELECTED` with why it matters, what the retained chain does identify (read back from the chain record by test, not restated), what is missing, which cells it blocks and how to select one. Since then it is `state: SELECTED`: a flat `selected_version` record pinning the receipt example's synthetic fixture by script digest and canonical content manifest, both recomputed from vendored artifacts on every build, with load job, validity window, expiry, `live_materialization: UNVERIFIED` and `historical_chain_equivalence: UNPROVEN` recorded, plus a separate `customer_data` block that keeps the Alder cohort `NOT SELECTED` (`spec-sqlchain-fact-select.md`). `validate_plan` refuses a missing state, a `SELECTED` state with no recorded version, a bare-label version, a wrong or truncated digest, a drifted manifest, a record that disagrees with the retained chain, one that still blocks cells, an unexplained `UNSELECTED` state, or a `blocks` list naming a cell that does not exist. Both states render: the Markdown reports the plan's actual state, prints the version field by field and drops the unselected-only sections, so a selection cannot leave the JSON card and the Markdown card disagreeing.
- Three recorded prior SQL observations are read out of the retained evidence and carried beside the cells with `fills_cell: false`.

Acceptance: every cell `INCOMPLETE`, every cost cell `UNMEASURED`, no prior observation filling a cell, the two consumer cells carrying `fact_version_blocked` with a stated reason while the plan was `UNSELECTED` and `NOT_IMPLEMENTED` alone once it was `SELECTED` (`RUNNER_HERMETIC_ONLY` since the hermetic-only runner landed on 2026-09-09, still a refusal), no surface saying failed attempts are "included in the denominator", and the committed artifacts byte-identical to their generator.

## 3. One correction the scaffold carries

`evidence/report.md` and `evidence/comparison.md` describe both forced fallback observations as on-demand. Every job in `all_all-0017.json#fallback_forced` carries the spike's Enterprise reservation. The scaffold reads the edition from the jobs in each record and states the discrepancy; the dated records are left as they are.

## 4. PR 45 honesty — three stale sentences

PR 45 (`ad18b07`) ran retrieval and the receipt check under `sa:okf-receipt-restricted` live: `CHAIN_CONNECTED`, four acceptances `MET`, 29 submitted jobs matched to the role that submitted them (20 requester, 9 operator administrative), reconciled against a drained job listing, teardown `VERIFIED`. Three page sentences predate it.

- Closed skim: "what we still need to prove: the same chain … for a second identity and a policy decision" → one chain that does catalog discovery, a restricted identity and graph queries **at once**, on real cohort data.
- Access section: "Work since then on a deliberately restricted requester exists only as offline tests" → it has now run live, naming the three refusals inside that chain, the hand-chosen seed, plain SQL and the same invented data.
- Evidence bar: "the separate-identity checks cover the other three tests, each in isolation and outside any chain" → five in isolation on 6 September, plus the 7 September restricted chain; **no single chain has yet done both** a live catalog read and a second identity.

Not claimed: a catalog read on the restricted chain, graph queries, an independent attester, real cohort data, or any score movement.

## 5. Links

Board-pack evidence links are pinned GitHub blob URLs at the revision that produced the artifact. The new baseline card
has no such revision — it is introduced by this PR — so the card links to it by **relative published path**
(`../spikes/bq-graph/evidence/sql-baseline/baseline.md`). That resolves inside the repository today and on the published
site once this PR merges; GitHub Pages serves the tree with `.nojekyll` and returns `text/markdown` for it. A pinned URL
at the predecessor revision returned 404, and a branch-ref URL would break when the branch is deleted.
