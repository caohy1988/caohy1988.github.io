# Story — five minutes before the board meeting

**Illustrative scenario.** Alder, its Finance VP, the quote, spending proposal and figures are invented. They are not identified customer evidence or a real deployment.

**Tone.** The reader-facing page is a leadership story, told once: the problem, what the product would do, what we know works, what is still open, and the decision. It carries no scoreboard labels, no pull-request numbers or commit hashes, no personal names or handles, and no lab calendar — capabilities and limits replace dated run logs, and the detail sits behind friendly evidence links. Every limit stays beside the claim it limits.

## The scene and arithmetic

The VP of Finance at subscription software company Alder checks the board pack at 8:55 a.m. before a 9 a.m. meeting. A $4 million plan to expand sales to existing customers rests on an agent's claim of 118% retention, labeled “verified.” An analyst catches the inclusion of new customers. The VP pulls the slide; the investment needs a different justification.

The agent found Finance's definition but missed the accompanying rule: count revenue only from customers there at the start. It reused a total-ARR query, and she cannot trace which policy allowed this agent to use that asset. The “verified” label has no execution receipt connecting the query, the declared retention calculation and the reported result. These are the three unanswered questions after she pulls the slide: a missing linked rule, access not explainable, execution not proven. The access gap is missing explanation, not evidence of forbidden access.

New sales hid a decline among the opening customer cohort. All amounts below are annual recurring revenue (ARR), measured at the opening and close of one illustrative quarter.

| Input | Amount |
| --- | ---: |
| Opening ARR of the starting customer cohort | $10.0m |
| Closing ARR from the same customers, including expansion, contraction and churn | $9.6m |
| Closing ARR from new customers | $2.2m |

The wrong calculation is `(9.6 + 2.2) / 10.0 = 118%`. Correct retention is `9.6 / 10.0 = 96%`: a 4% decline among existing customers. No query, receipt or attestation produced these hypothetical figures. The narrative does not assert the investment itself is necessarily bad.

## Why the graph matters before the calculation

Finance's agent needs a connected set of context: the approved retention definition, its starting-cohort rule and its declared computation. Citing the definition alone leaves room to use an unrelated total-ARR query. The proposed runtime retrieves that connected context through an explicit query against a pinned OKF publication, then separately runs and accounts for the metric computation.

The BigQuery case begins with knowledge retrieval. It is especially strong for analytical agents whose relevant facts already live in BigQuery, on Enterprise or Enterprise Plus capacity, within latency, freshness, concurrency and cost budgets the customer has agreed to. No customer has agreed such a budget yet. The page makes no claim about where fictional Alder keeps its revenue tables.

## Three distinct advantages — proposed runtime

Keep the service roles in one short introduction: Knowledge Catalog discovers/governs; OKF authors the graph. Replace the page's former role cards with three paired comparisons of **KC + OKF** and **+ BQ runtime**. Each pair carries one story takeaway.

1. **Replayable context:** KC discovery and authored OKF relations leave context assembly to the retriever. The BigQuery projection, pinned publication and explicit SQL/bounded walks select the retention definition, cohort rule and declared computation together. This controls the context received by the agent, not the computation it ultimately executes.
2. **Explainable access:** custom entries use an EntryGroup access boundary today; that is not a universal statement about all KC permissions. The proposed runtime joins identity, policy and projected assets, binds the authenticated requester to the execution identity, enforces access along the retrieval path and records returned nodes. The payoff is explaining why Finance's agent could use the total-ARR asset. No unauthorized access is asserted.
3. **Verifiable execution:** finding Finance's declaration does not establish that retention was computed. Run the metric and validate a job ↔ context ↔ result receipt against that declaration. A total-ARR substitution or missing evidence leaves the claim unproven. This closes the near-miss in the story and is distinct from context replay and permission evaluation.

Access relationships stored as metadata are not authorization controls by themselves. Source permissions must stay current; metadata visibility does not grant access to the underlying file. A shared service account alone does not identify the requesting user or agent. Per-node enforcement and the requester/execution binding are proposed integration work, not a built property of Graph-over-OKF. Historical context pins must never bypass current authorization.

## Determinism is a contract, not a slogan

“Same inputs → same context and result shape” requires a deterministic query, fixed publication, query parameters, fact versions, authorization scope and stable ordering. Avoid volatile functions, unstable tie handling and unversioned external inputs. Graph-walk bounds and the returned schema are explicit. An immutable context publication alone does not freeze mutable fact tables or access policy.

Vector similarity ranks likely passages; an LLM can choose different excerpts or paths. Vector retrieval is not inherently nondeterministic. The distinction is explicit, inspectable traversal semantics over versioned graph inputs. The guarantee covers context retrieval, not identical model answers, business truth or permission bypass.

A retrieval receipt records how context was selected. It does not prove that the retention computation ran or returned 96%. The pilot must test both the retrieval contract and the separate computation-evidence boundary. Withhold execution evidence and the number stays unproven.

## Capacity and the first-workload route

Graph walks (GQL) require Enterprise or Enterprise Plus capacity; ordinary relational SQL and vector retrieval also run on-demand. A projected graph can be the first workload on such capacity after its inputs are loaded, but the strongest case remains a customer whose facts are already in BigQuery, and the page says so. If no graph or facts enter BigQuery, no BigQuery retrieval occurs.

The OKF bundle remains the authored source. Catalog and BigQuery are projections with different roles. Do not imply an implemented Catalog-to-BigQuery import or change the full RFC's source-bundle authority. A source pin is not a working live KC discovery integration; the connected runs read a live catalog entry to confirm which publication to pin, which is narrower than an implemented Catalog-to-BigQuery import.

## What the experiments establish

Every recorded experiment ran on invented gross-margin data for a company called Acme. None ran the Alder story or produced its retention figures. The page states these as capabilities and limits, not as a run log: it carries no lab calendar, no job counts and no personal names, and the detail sits behind friendly evidence links.

**What is known to work.** Retrieval can select a definition together with the rules it links to. A receipt can bind a query to its result and withhold the number when they disagree. The whole path has run end to end — governed retrieval into a checked computation into a consumer that releases nothing unless the check passes — including one run whose retrieval went through graph queries on Enterprise capacity — that one under a single identity, from a starting point we chose rather than one discovered through the catalog, and only for the case expected to succeed. A separate restricted identity was denied where it should be on the ordinary SQL path, and connected runs also held their pinned version against a republished head and refused self-tampered payloads.

**What limits every one of those statements.** The graph-query run carried a single identity on both legs, started from a point we chose rather than one discovered through the catalog, and exercised only the case expected to succeed — so refusal behaviour has not been shown through graph queries. The restricted-identity run also started from a chosen point. The catalog-seeded runs carried a single identity on plain SQL. The access denials have not been repeated inside graph queries. The catalog read is our own, seeded for the experiment. No run used an independent attester, real cohort data, or Alder’s retention.

**The bar is unchanged.** Catalog discovery, a separate restricted identity and graph queries have never been combined in one run, on real data. Three results each reach a different part of it and no single run has done two, let alone all three. Speed benchmarks are unfinished — none of the nine planned cells is complete — and the ordinary-SQL comparison remains a declared plan with no numbers in it. Receipt work should not wait for the graph benchmark.
## The decision checkpoint and its proposed envelope

The page carries a visible evaluation card (`#sep19-envelope`) so the checkpoint is a workload decision rather than more demonstration prose. **Owner: the project owner, named in the decision record and not on the reader-facing page.** He has not accepted any threshold, and no Finance or data owner outside this project has been asked for one; naming an owner is not agreeing an envelope. Every threshold below is therefore **PROPOSED**, and the historical p95 of 5.4 s is explicitly not an agreement.

| Field | Value | Status |
| --- | --- | --- |
| Task | An analyst's agent retrieves a pinned definition, its linked rules and the declared calculation, and releases a number only on a receipt bound to that calculation | PROPOSED |
| Corpus and definition versions | `acme_retail` at publication `pub_190192147fd7fd78`, source pin `31da799a`, 17 documents + 2 artifacts, question set at `as_of` 2026-09-05. Fixes the authored definitions and the graph projection they compile to; identifies no fact data | FIXED (what every experiment retrieved from) |
| Fact data and its version | The retained chain names the receipt example's own fixture — 7 tables in `test-project-0728-467323.okf_receipt_spike_20260905`, reached through publication `okf-receipt-spike/acme-retail-derived/gross-margin-period` at SDK pin `6719eb5`, a separate identity from the graph publication and joined to it only by the declaration file's bytes — but pins no snapshot, no as-of and no row version for them; the chain's own `as_of` is its run timestamp. Alder cohort data has never been selected | **UNSELECTED / INCOMPLETE** — a prerequisite for the request-to-consumer comparison, and it blocks `sqlchain_forced_c1` / `sqlchain_forced_c5` |
| Concurrency | 5 concurrent requests; C=1 is the only concurrency any recorded observation covers | PROPOSED (planning default) |
| Request volume | 10,000 requests/day | PROPOSED, never modelled |
| Tolerated latency | Retrieval p95 ≤ 5 s at C=5. Reported separately from full request-to-consumer time, for which no threshold is proposed because nothing has sampled it | PROPOSED |
| Freshness | Republished definition visible to new requests ≤ 60 s (one publish took 21.3 s, n=1). An in-flight request keeps its pinned publication, by design and tested | PROPOSED |
| Retention | 15 months of context, access and receipt records, so a board-pack number is still explainable at the next annual close. No measurement behind the horizon | PROPOSED |
| Success definition | ≥99% of requests either release a number whose receipt verifies or refuse with a stated reason; zero releases without a verifying receipt; zero disclosures of denied content | PROPOSED |
| Total-cost ceiling | ≤ $0.05 per answered question at 10,000/day, including failed and refused attempts, embeddings, storage, publication upkeep and any reserved capacity | PROPOSED, nothing measured against it |
| Owner | The project owner (named in the decision record, not on the page) | Has accepted no threshold |

**Decision rule.** At the upcoming checkpoint we continue, narrow or stop against whichever thresholds the owner has accepted by then. If ordinary SQL meets the need, graph queries must justify their additional cost. If nobody accepts the envelope, the scoped opportunity narrows — more demonstration evidence is not pilot validation.

**Matched baseline.** The ordinary-SQL comparison is predeclared and empty: `rfc/spikes/bq-graph/evidence/sql-baseline/baseline.md`, generated from `fixtures/sql_baseline.json`. Four retrieval cells at C=1 and C=5 across the forced-seed and natural-question shapes, two request-to-consumer cells with no runner yet **and no selected fact version**, five unmeasured cost cells (cost per success = total cost of all attempts ÷ released, receipt-verified answers), and a budget projection against declared ceilings. Three recorded prior SQL observations are carried beside the cells and fill none of them. Any GQL comparison is optional and later, and must match this seed shape, corpus, authorization and workload with its reservation cost accounted separately.

## The story skim and punchline

Keep the Finance VP, Alder, the five-minute deadline, $4 million decision, 118% and 96% in the hero. One arithmetic figure makes the new-customer mistake visible. The near-miss previews all three unanswered questions in one short paragraph; the runtime comparison answers them in the same order. On mobile, each labeled KC + OKF / + BQ pair stays together. One Finance pilot connects pinned retrieval, current authorization and result-bound consumption. Use a neutral title, pilot eyebrow and RFC link label; the page is a customer/runtime brief, not addressed to a named product-executive audience.

**Later-audit beat.** After the three comparisons and before the capacity line, one short visible panel asks what Finance could still ask later, in the same order: which definition, cohort rule and calculation the agent received (a saved context record); which identity and policy permitted access at the time (a protected access record, readable later only with permission); and whether the job matched Finance's declared calculation and the displayed number (a checked execution receipt showing evidence, a mismatch, or why the result remains unproven). The panel is conditional: these are goals for the connected pilot, each answer holds only while the evidence is retained and the reader is permitted to see it now, and none explains the model's private reasoning. It adds no fourth outcome, no new score and no shipped-feature claim; the Technical design already explains each mechanism.

**The proposed BigQuery runtime would turn the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.**

Graph-over-OKF as a connected runtime, per-node authorization, and governed sync remain proposals; the recorded experiments supply narrow retrieval and receipt evidence, linked in plain words beside each claim. Existing full-demo captures concern a different scenario and do not prove this graph retrieval or the Alder figures. The page ends with the pilot ask: one Finance-owned pilot on real cohort data with an agreed operating budget, where a wrong query or missing evidence withholds the claim; 96% is not a real-data acceptance target. Keep the hero's illustrative label, the runtime's proposed/early-experiments labels and the comparison notes; no footer or evidence appendix is required.

## Optional design detail and public address

The brief lives at `/rfc/board-pack/`, with Board-pack near-miss → as its RFC index label. The legacy `/rfc/bq-vp/` address only redirects there.

Place one closed-by-default Technical design disclosure after the comparisons and first-workload line, before the punchline. It expands the same three mechanisms: retrieve Finance's linked rules under fixed inputs and bounded traversal; enforce current access for an authenticated requester; separately validate the computation job against the declared calculation. Include the graph projection's relationship to the authored OKF bundle, receipt contents and current-authorization boundary, then a short where-the-evidence-stands section with the review status, open graph items and the connected-path bar, written in plain words. The diagram is a proposed connected design; a narrower version of its arrows (live catalog read through pinned publication to enforcing consumer, one operator on both legs, plain SQL in place of graph queries) has been exercised on Acme, the full design has not, and its 96% pass is illustrative. The closed page preserves the story skim; keyboard users can expand the detail, and print includes it regardless of screen state.
