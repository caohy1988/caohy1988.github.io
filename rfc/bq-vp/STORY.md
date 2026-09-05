# Story — five minutes before the board meeting

**Illustrative scenario.** Alder, Maya, the quote, spending proposal and figures are invented. They are not identified customer evidence or a real deployment.

## The scene and arithmetic

Maya Chen, VP of Finance at subscription software company Alder, checks the board pack at 8:55 a.m. before a 9 a.m. meeting. A $4 million plan to expand sales to existing customers rests on an agent's claim of 118% retention, labeled “verified.” An analyst catches the inclusion of new customers. Maya pulls the slide; the investment needs a different justification.

The agent found Finance's definition but missed the accompanying rule: count revenue only from customers there at the start. It reused a total-ARR query. Maya cannot trace which policy allowed this agent to use that asset. The “verified” label has no execution receipt connecting the query, the declared retention calculation and the reported result. These are the three unanswered questions after she pulls the slide: a missing linked rule, access not explainable, execution not proven. The access gap is missing explanation, not evidence of forbidden access.

New sales hid a decline among the opening customer cohort. All amounts below are annual recurring revenue (ARR), measured at the opening and close of one illustrative quarter.

| Input | Amount |
| --- | ---: |
| Opening ARR of the starting customer cohort | $10.0m |
| Closing ARR from the same customers, including expansion, contraction and churn | $9.6m |
| Closing ARR from new customers | $2.2m |

The wrong calculation is `(9.6 + 2.2) / 10.0 = 118%`. Correct retention is `9.6 / 10.0 = 96%`: a 4% decline among existing customers. No query, receipt or attestation produced these hypothetical figures. The narrative does not assert the investment itself is necessarily bad.

## Why the graph matters before the calculation

Maya's agent needs a connected set of context: the approved retention definition, its starting-cohort rule and its declared computation. Citing the definition alone leaves room to use an unrelated total-ARR query. The proposed runtime retrieves that connected context through an explicit query against a pinned OKF publication, then separately runs and accounts for the metric computation.

The revised BigQuery case begins with knowledge retrieval. It does not depend on Alder already having revenue tables in BigQuery. Existing data placement is not part of the page's argument.

## Three distinct advantages — proposed runtime

Keep the service roles in one short introduction: Knowledge Catalog discovers/governs; OKF authors the graph. Replace the page's former role cards with three paired comparisons of **KC + OKF** and **+ BQ runtime**. Each pair carries one story takeaway.

1. **Replayable context:** KC discovery and authored OKF relations leave context assembly to the retriever. The BigQuery projection, pinned publication and explicit SQL/bounded walks select the retention definition, cohort rule and declared computation together. This controls the context received by the agent, not the computation it ultimately executes.
2. **Explainable access:** custom entries use an EntryGroup access boundary today; that is not a universal statement about all KC permissions. The proposed runtime joins identity, policy and projected assets, binds the authenticated requester to the execution identity, enforces access along the retrieval path and records returned nodes. The payoff is explaining why Maya's agent could use the total-ARR asset. No unauthorized access is asserted.
3. **Verifiable execution:** finding Finance's declaration does not establish that retention was computed. Run the metric and validate a job ↔ context ↔ result receipt against that declaration. A total-ARR substitution or missing evidence leaves the claim unproven. This closes Maya's actual near-miss and is distinct from context replay and permission evaluation.

Access relationships stored as metadata are not authorization controls by themselves. Source permissions must stay current; metadata visibility does not grant access to the underlying file. A shared service account alone does not identify the requesting user or agent. Per-node enforcement and the requester/execution binding are proposed integration work, not a built property of Graph-over-OKF. Historical context pins must never bypass current authorization.

## Determinism is a contract, not a slogan

“Same inputs → same context and result shape” requires a deterministic query, fixed publication, query parameters, fact versions, authorization scope and stable ordering. Avoid volatile functions, unstable tie handling and unversioned external inputs. Graph-walk bounds and the returned schema are explicit. An immutable context publication alone does not freeze mutable fact tables or access policy.

Vector similarity ranks likely passages; an LLM can choose different excerpts or paths. Vector retrieval is not inherently nondeterministic. The distinction is explicit, inspectable traversal semantics over versioned graph inputs. The guarantee covers context retrieval, not identical model answers, business truth or permission bypass.

A retrieval receipt records how context was selected. It does not prove that the retention computation ran or returned 96%. The pilot must test both the retrieval contract and the separate computation-evidence boundary. Withhold execution evidence and the number stays unproven.

## Starting with an empty BigQuery project

Land the OKF graph projection and version any facts retrieval needs in BigQuery. The knowledge graph can be the first workload, before a revenue warehouse exists. If no graph or facts enter BigQuery, no BigQuery retrieval occurs. The page proposes this architectural step; it does not claim that OKF or Catalog inherently require BigQuery for every use.

The OKF bundle remains the authored source. Catalog and BigQuery are projections with different roles. Do not imply an implemented Catalog-to-BigQuery import or change the full RFC's source-bundle authority.

## The story skim and punchline

Keep Maya, Alder, the five-minute deadline, $4 million decision, 118% and 96% in the hero. One arithmetic figure makes the new-customer mistake visible. The near-miss previews all three unanswered questions in one short paragraph; the runtime comparison answers them in the same order. On mobile, each labeled KC + OKF / + BQ pair stays together. One Finance pilot tests retrieval, access boundaries and computation evidence. Use a neutral title, pilot eyebrow and RFC link label; the page is a customer/runtime brief, not addressed to a named product-executive audience.

**BigQuery turns the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.**

Graph-over-OKF, per-node authorization, validated receipts and the governed runtime remain RFC proposals. Existing full-demo captures concern a different scenario and do not prove this graph retrieval or the Alder figures. Keep them as an optional evidence deep dive, with the unbuilt/stub boundaries in the page footer.
