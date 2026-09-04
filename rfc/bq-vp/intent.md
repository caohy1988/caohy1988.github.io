# Intent — the board meets at 9

## Audience and problem

A BigQuery VP should grasp the customer moment in 30 seconds and understand why BigQuery is the runtime for Knowledge Catalog + OKF in two to three minutes. The previous page led with a runtime thesis, three abstract benefits and a thin Germany revenue question. Replace it with a complete illustrative near-miss, readable in two to three minutes on one continuous page.

## Chosen story

At 8:55 a.m., Maya Chen, VP of Finance at fictional subscription software company Alder, sees 118% net revenue retention in a board pack supporting a $4 million customer-expansion plan. An analyst catches the inclusion of new customers. The opening cohort retained 96%; Maya pulls the slide before the 9 a.m. meeting.

The agent reused a total-ARR query and cited the retention definition without connecting that definition to its computation. The arithmetic, stakes and human intervention must be understandable before the runtime proposal appears. See `STORY.md` for the scenario and rationale.

## The opportunity and ask

Make the roles explicit: Catalog finds the approved definition; OKF supplies the authored definition, query and parameters that the runtime pins; BigQuery runs the computation and binds job, context, parameters and result in a receipt. Catalog discovery alone does not execute the query or produce that receipt.

Alder's revenue data is already in BigQuery in this scenario. The proposed runtime places computation and evidence beside the data, job records and access controls. Explain attribution as the agent plus the identity running the job, and IAM as who can publish context, execute the query and read evidence.

The repeatable punchline is: **Find it in Catalog. Run it in BigQuery. Bring the receipt.**

Ask the VP to sponsor one retention pilot with a Finance owner, using one quarter of cohort data and a missing-receipt negative case.

## Honesty and scope

Alder, Maya, the quotation and every number are invented. Label that before the story. The proposed runtime did not produce 96%; it is illustrative arithmetic. Existing full-demo recordings concern a different scenario and are only an optional evidence deep dive. No customer claim, new cloud execution, successful attestation, completed sync or Phase A IAM is implied.

Sharpen the page and its local documentation on the existing `feat/rfc-bq-vp-story` branch. Keep the RFC entry link accurate and the full demo unchanged. Commit and push to PR 20, preserve the session record under `/tmp/okf-vp-story/`, and report the new HEAD. Do not create another PR or merge.
