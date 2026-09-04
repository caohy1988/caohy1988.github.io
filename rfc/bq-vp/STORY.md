# Story — five minutes before the board meeting

**Illustrative scenario.** The company, people, quote, spending proposal and figures are invented. They are not a composite of identified customer evidence and do not describe a real customer deployment.

## The scene

Alder sells subscription software. Maya Chen, its VP of Finance, is checking the board pack at 8:55 a.m. before a 9 a.m. meeting. A proposed $4 million customer-expansion plan is justified by a claim that existing customers are growing. The finance agent has supplied: “118% net revenue retention. Verified.”

An analyst asks whether new customers were included. The agent reused an old total-ARR query and labeled the result retention. A citation to Finance's metric page made the answer appear checked; no computation receipt bound the cited definition to the number. Maya pulls the slide. The spending proposal now needs another justification; the story does not assert that the investment itself is necessarily bad.

## The arithmetic

All amounts are annual recurring revenue (ARR), measured at the opening and close of one illustrative quarter. The opening cohort is fixed by customer identity.

| Input | Amount |
| --- | ---: |
| ARR of the opening customer cohort at the start | $10.0m |
| ARR from those same customers at quarter end, including their expansion, contraction and churn | $9.6m |
| ARR from customers acquired during the quarter | $2.2m |

The wrong result is total closing ARR divided by opening ARR: `(9.6 + 2.2) / 10.0 = 118%`. Correct retention for the opening cohort is `9.6 / 10.0 = 96%`. New business masked a 4% decline among existing customers. There is no invented SQL run, job ID, receipt or attestation supporting these hypothetical numbers.

## The proposed counterfactual — three beats

1. **Discover:** Knowledge Catalog points to Finance's approved retention definition and computation authored in Open Knowledge Format (OKF). The definition excludes new customers. Discovery is not evidence that this computation ran.
2. **Pin and compute:** The proposed BigQuery runtime resolves and holds the context publication fixed, executes the declared cohort query with the quarter parameters, and binds the publication, parameters, job and result in a computation receipt. Missing execution evidence leaves the answer unproven. The pinned publication is a context revision, not a frozen copy of the revenue data; the pilot must retain or explicitly identify its input data for replay.
3. **Attribute:** A reviewer follows the answer to the agent, execution identity, context and receipt under explicit access grants. Context retention preserves what was used when Finance later revises its definition. It does not guarantee every model gives the same answer, establish business truth, or make unauthorized data available.

The authored OKF bundle remains the source; Catalog and BigQuery are projections with different roles. The story must not imply Catalog-to-BigQuery import is built or is the v1 publication direction. The full RFC owns the sync and authorization design.

## Why this story

The clock and board pack give the VP a recognizable moment. The 118% → 96% correction is memorable and independently checkable without data-platform expertise. The near-miss separates finding a definition from proving that the answer used it. Three runtime responsibilities resolve the same incident, and the ask is one measurable pilot.

Repeatable sentence: **An agent’s boardroom number should come with a BigQuery receipt.**

The original Germany captures remain in `/rfc/full-demo/`; they illustrate implementation status and failure modes, not this scenario. No session ID is repurposed as evidence for Alder.
