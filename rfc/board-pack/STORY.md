# Story — five minutes before the board meeting

**Illustrative scenario.** Alder, Maya, the quote, spending proposal and figures are invented. They are not identified customer evidence or a real deployment.

**Tone (2026-09-06 pass).** The reader-facing page uses plain language: what works today, what we still need to prove, what the Finance pilot is for. It carries no scoreboard labels, pull-request numbers, commit hashes or internal gate codes; evidence links use friendly text and point at the same recorded artifacts. The underlying claims and limits are unchanged.

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

The BigQuery case begins with knowledge retrieval. It is especially strong for analytical agents whose relevant facts already live in BigQuery, on Enterprise or Enterprise Plus capacity, within latency, freshness, concurrency and cost budgets the customer has agreed to. No customer has agreed such a budget yet. The page makes no claim about where fictional Alder keeps its revenue tables.

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

## Capacity and the first-workload route

Graph walks (GQL) require Enterprise or Enterprise Plus capacity; ordinary relational SQL and vector retrieval also run on-demand. A projected graph can be the first workload on such capacity after its inputs are loaded, but the strongest case remains a customer whose facts are already in BigQuery, and the page says so. If no graph or facts enter BigQuery, no BigQuery retrieval occurs.

The OKF bundle remains the authored source. Catalog and BigQuery are projections with different roles. Do not imply an implemented Catalog-to-BigQuery import or change the full RFC's source-bundle authority. A source pin is not a working live KC discovery integration.

## What the early experiments establish (2026-09-06)

Two separate recorded experiments exist, both run on invented gross-margin data for a company called Acme. Neither ran the Alder story or produced its retention figures.

- **Receipt check** ([recorded evidence](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/blob/6719eb535667963fa640dd4535e508b550eb6cb1/examples/okf_attested_computation/evidence/receipt/report.md)): a BigQuery job owned by the caller, the job and result read back from BigQuery itself, verification in a fresh process, and a consumer that released the result only after the check passed. Wrong-query, wrong-parameter, tampered, replayed and missing-evidence cases released nothing. This is one worked example, not a library feature, product release or independent verifier. A passed check is an evidence verdict for that example only.
- **Graph walk** ([recorded results](https://github.com/caohy1988/caohy1988.github.io/blob/b05e278b0c459f3dc035d7cae48841c75d6fa89f/rfc/spikes/bq-graph/evidence/report.md)): run on a measured Enterprise reservation. Starting from a retired definition it followed two links to the sanctioned SQL, produced an impact list matching a relational cross-check, and handled placeholder, ambiguous and out-of-scope entries on a deliberately awkward test bundle (Acme's own backlog had no placeholders). Its report counts this as demonstrated retrieval only: the SQL it returned was found, not run. The access checks are unfinished (per-requester authorization and publication consistency partly tested, two-requester tests could not run), and the speed benchmarks are not finished yet (0 of 9 cells complete). The reservation was recorded as torn down; that is not an audit of every job or fixture resource.
- **The connected path is still to prove.** We will call it proven only after one chain runs end to end: catalog discovery, pinned publication, governed retrieval, computation delegated by the caller, a receipt bound to the result, and a consumer that enforces it, plus tests for publication consistency, denied intermediate nodes, revocation before cached replay and unauthorized output. Receipt work should not wait for the graph benchmark. We reassess the opportunity at the 2026-09-19 checkpoint; it narrows if budgets or Enterprise cost prove unacceptable, simpler retrieval meets the need, semantics, authorization or publication guarantees fail, or result evidence cannot be bound and enforced.

The wider demo's computation checks are still placeholders, so its receipts cannot be verified yet; that boundary is separate from the recorded example's evidence.

## The story skim and punchline

Keep Maya, Alder, the five-minute deadline, $4 million decision, 118% and 96% in the hero. One arithmetic figure makes the new-customer mistake visible. The near-miss previews all three unanswered questions in one short paragraph; the runtime comparison answers them in the same order. On mobile, each labeled KC + OKF / + BQ pair stays together. One Finance pilot connects pinned retrieval, current authorization and result-bound consumption. Use a neutral title, pilot eyebrow and RFC link label; the page is a customer/runtime brief, not addressed to a named product-executive audience.

**Later-audit beat (2026-09-06).** After the three comparisons and before the capacity line, one short visible panel asks what Maya could still ask later, in the same order: which definition, cohort rule and calculation the agent received (a saved context record); which identity and policy permitted access at the time (a protected access record, readable later only with permission); and whether the job matched Finance's declared calculation and the displayed number (a checked execution receipt showing evidence, a mismatch, or why the result remains unproven). The panel is conditional: these are goals for the connected pilot, each answer holds only while the evidence is retained and the reader is permitted to see it now, and none explains the model's private reasoning. It adds no fourth outcome, no new score and no shipped-feature claim; the Technical design already explains each mechanism.

**The proposed BigQuery runtime would turn the OKF graph into replayable context for agents—with explainable access and evidence that the declared computation ran.**

Graph-over-OKF as a connected runtime, per-node authorization, and governed sync remain proposals; the recorded experiments supply narrow retrieval and receipt evidence, linked in plain words beside each claim. Existing full-demo captures concern a different scenario and do not prove this graph retrieval or the Alder figures. The page ends with the pilot ask: one Finance-owned pilot on real cohort data with an agreed operating budget, where a wrong query or missing evidence withholds the claim; 96% is not a real-data acceptance target. Keep the hero's illustrative label, the runtime's proposed/early-experiments labels and the comparison notes; no footer or evidence appendix is required.

## Optional design detail and public address

The brief lives at `/rfc/board-pack/`, with Board-pack near-miss → as its RFC index label. The legacy `/rfc/bq-vp/` address only redirects there.

Place one closed-by-default Technical design disclosure after the comparisons and first-workload line, before the punchline. It expands the same three mechanisms: retrieve Finance's linked rules under fixed inputs and bounded traversal; enforce current access for an authenticated requester; separately validate the computation job against the declared calculation. Include the graph projection's relationship to the authored OKF bundle, receipt contents and current-authorization boundary, then a short where-the-evidence-stands section with the review status, open graph items and the connected-path bar, written in plain words. The diagram is a proposed connected design; its arrows have not been exercised as one path, and its 96% pass is illustrative. The closed page preserves the story skim; keyboard users can expand the detail, and print includes it regardless of screen state.
