# Story — five minutes before the board meeting

**Illustrative scenario.** The company, people, quote, spending proposal and figures are invented. They are not a composite of identified customer evidence and do not describe a real customer deployment.

## The scene

Alder sells subscription software and keeps its revenue data in BigQuery. This data location is part of the invented scenario, not a checked-in customer claim. Maya Chen, its VP of Finance, is checking the board pack at 8:55 a.m. before a 9 a.m. meeting. A proposed $4 million customer-expansion plan is justified by a claim that existing customers are growing. The finance agent has supplied: “118% net revenue retention. Verified.”

An analyst asks whether new customers were included. The agent reused an old total-ARR query and labeled the result retention. A citation to Finance's metric page made the answer appear checked; no computation receipt bound the cited definition to the number. Maya pulls the slide. The spending proposal now needs another justification; the story does not assert that the investment itself is necessarily bad.

## The arithmetic

All amounts are annual recurring revenue (ARR), measured at the opening and close of one illustrative quarter. The opening cohort is fixed by customer identity.

| Input | Amount |
| --- | ---: |
| ARR of the opening customer cohort at the start | $10.0m |
| ARR from those same customers at quarter end, including their expansion, contraction and churn | $9.6m |
| ARR from customers acquired during the quarter | $2.2m |

The wrong result is total closing ARR divided by opening ARR: `(9.6 + 2.2) / 10.0 = 118%`. Correct retention for the opening cohort is `9.6 / 10.0 = 96%`. New business masked a 4% decline among existing customers. There is no invented SQL run, job ID, receipt or attestation supporting these hypothetical numbers.

## The proposed runtime — three distinct roles

1. **Knowledge Catalog finds the definition.** Discover Finance's approved retention metric. A definition lookup neither executes the cohort query nor produces a computation receipt proving that the answer used it.
2. **OKF specifies the instructions.** Finance authors the definition, declared query and parameters in an Open Knowledge Format bundle. The proposed runtime pins one revision for the run. OKF is the authored content; it is not itself an execution or pinning service.
3. **BigQuery runs it and accounts for it.** Alder's revenue tables, query jobs and data access controls already live here. The proposed runtime executes the declared query there and binds job, pinned context, quarter parameters and result in a computation receipt. Attribution connects the answer to its agent and execution identity; IAM separates publishing context, running the query and reading evidence. Missing execution evidence means unproven.

A pinned context revision does not freeze the revenue data. The pilot must retain or identify its input data for replay. An execution receipt does not establish business truth or grant access. The claim for BigQuery is its additional role relative to Catalog discovery, not that no other database can execute SQL.
The authored OKF bundle remains the source; Catalog and BigQuery are projections with different roles. The story must not imply Catalog-to-BigQuery import is built or is the v1 publication direction. The full RFC owns the sync and authorization design.

## Why this story

The clock and board pack give the VP a recognizable moment. The 118% → 96% correction is memorable and independently checkable without data-platform expertise. The near-miss separates finding a definition from proving that the answer used it. Three named roles explain why finding the approved definition alone cannot fix this incident. BigQuery is given the most space because execution, receipts, attribution and access control are the missing runtime responsibilities. The ask remains one measurable pilot.

Repeatable line: **Find it in Catalog. Run it in BigQuery. Bring the receipt.**

The original Germany captures remain in `/rfc/full-demo/`; they illustrate implementation status and failure modes, not this scenario. No session ID is repurposed as evidence for Alder.

## 30-second skim, sharpened on 2026-09-04

The hero itself must contain Maya, Alder, the five-minute deadline, the $4 million decision, 118% and 96%, before any architecture language. The single arithmetic figure labels the $2.2m of new-customer ARR as the wrong addition and contrasts it with same-customer retention. A reader can see the error without the story paragraph.

Story prose is direct because the illustrative label establishes its status. The technical section is explicitly an unbuilt RFC proposal; its imperative descriptions are proposed responsibilities, not shipped-service claims. Keep the detailed evidence limitations in the footer.
