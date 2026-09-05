# Story — five minutes before the board meeting

**Illustrative scenario.** Alder, Maya, the quote, spending proposal and figures are invented. They are not identified customer evidence or a real deployment.

## The scene and arithmetic

Maya Chen, VP of Finance at subscription software company Alder, checks the board pack at 8:55 a.m. before a 9 a.m. meeting. A $4 million plan to expand sales to existing customers rests on an agent's claim of 118% retention, labeled “verified.” An analyst catches the inclusion of new customers. Maya pulls the slide; the investment needs a different justification.

The agent cited Finance's definition but reused a total-ARR query. New sales hid a decline among the opening customer cohort. All amounts below are annual recurring revenue (ARR), measured at the opening and close of one illustrative quarter.

| Input | Amount |
| --- | ---: |
| Opening ARR of the starting customer cohort | $10.0m |
| Closing ARR from the same customers, including expansion, contraction and churn | $9.6m |
| Closing ARR from new customers | $2.2m |

The wrong calculation is `(9.6 + 2.2) / 10.0 = 118%`. Correct retention is `9.6 / 10.0 = 96%`: a 4% decline among existing customers. No query, receipt or attestation produced these hypothetical figures. The narrative does not assert the investment itself is necessarily bad.

## Why the graph matters before the calculation

Maya's agent needs a connected set of context: the approved retention definition, its starting-cohort rule and its declared computation. Citing the definition alone leaves room to use an unrelated total-ARR query. The proposed runtime retrieves that connected context through an explicit query against a pinned OKF publication, then separately runs and accounts for the metric computation.

The revised BigQuery case begins with knowledge retrieval. It does not depend on Alder already having revenue tables in BigQuery. Existing data placement is not part of the page's argument.

## Three distinct roles — proposed runtime

1. **Knowledge Catalog discovers and governs.** Find Finance's approved concept and its owner. Discovery of an entry is different from deterministically traversing the linked OKF graph to select an agent's context.
2. **OKF authors the graph.** Definitions, relationships, computation declarations and versions are authored in an Open Knowledge Format bundle. OKF supplies the graph and context; the format itself is not a query engine for agents at scale or pinning service.
3. **BigQuery projects and retrieves.** Materialize the graph's nodes, edges, publication membership and related facts in queryable structures. Resolve one pinned publication, then use explicit SQL or bounded graph walks to retrieve the context. A proposed retrieval receipt records the query, pins and returned context. Metric execution follows separately, with a computation receipt connecting its job, context and result, plus agent/execution-identity attribution under IAM.

## Determinism is a contract, not a slogan

“Same inputs → same context and result shape” requires a deterministic query, fixed publication, query parameters, fact versions, authorization scope and stable ordering. Avoid volatile functions, unstable tie handling and unversioned external inputs. Graph-walk bounds and the returned schema are explicit. An immutable context publication alone does not freeze mutable fact tables or access policy.

Vector similarity ranks likely passages; an LLM can choose different excerpts or paths. Vector retrieval is not inherently nondeterministic. The distinction is explicit, inspectable traversal semantics over versioned graph inputs. The guarantee covers context retrieval, not identical model answers, business truth or permission bypass.

A retrieval receipt records how context was selected. It does not prove that the retention computation ran or returned 96%. The pilot must test both the retrieval contract and the separate computation-evidence boundary. Withhold execution evidence and the number stays unproven.

## Starting with an empty BigQuery project

Land the OKF graph projection and version any facts retrieval needs in BigQuery. The knowledge graph can be the first workload, before a revenue warehouse exists. If no graph or facts enter BigQuery, no BigQuery retrieval occurs. The page proposes this architectural step; it does not claim that OKF or Catalog inherently require BigQuery for every use.

The OKF bundle remains the authored source. Catalog and BigQuery are projections with different roles. Do not imply an implemented Catalog-to-BigQuery import or change the full RFC's source-bundle authority.

## The VP skim and punchline

Keep Maya, Alder, the five-minute deadline, $4 million decision, 118% and 96% in the hero, before architecture language. One arithmetic figure makes the new-customer mistake visible. The runtime section explains replayable retrieval first, using the same story's linked context. One Finance pilot is the ask.

**BigQuery turns the OKF graph into replayable context for agents.**

Graph-over-OKF, retrieval receipts and the governed runtime remain RFC proposals. Existing full-demo captures concern a different scenario and do not prove this graph retrieval or the Alder figures. Keep them as an optional evidence deep dive, with the unbuilt/stub boundaries in the page footer.
