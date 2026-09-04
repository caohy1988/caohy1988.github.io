# Intent — the board meets at 9

## Audience and problem

A BigQuery VP should be able to retell a customer moment after one skim. The previous page led with a runtime thesis, three abstract benefits and a thin Germany revenue question. Replace it with a complete illustrative near-miss, readable in two to three minutes on one continuous page.

## Chosen story

At 8:55 a.m., Maya Chen, VP of Finance at fictional subscription software company Alder, sees 118% net revenue retention in a board pack supporting a $4 million customer-expansion plan. An analyst catches the inclusion of new customers. The opening cohort retained 96%; Maya pulls the slide before the 9 a.m. meeting.

The agent reused a total-ARR query and cited the retention definition without connecting that definition to its computation. The arithmetic, stakes and human intervention must be understandable before the runtime proposal appears. See `STORY.md` for the scenario and rationale.

## The opportunity and ask

Knowledge Catalog would make Finance's approved OKF definition and declared computation discoverable. BigQuery would serve as the runtime: pin the context, run the computation, bind a receipt to the result, and support attribution to the agent and execution identity under explicit access grants.

The repeatable punchline is: **An agent’s boardroom number should come with a BigQuery receipt.**

Ask the VP to sponsor one retention pilot with a Finance owner, using one quarter of cohort data and a missing-receipt negative case.

## Honesty and scope

Alder, Maya, the quotation and every number are invented. Label that before the story. The proposed runtime did not produce 96%; it is illustrative arithmetic. Existing full-demo recordings concern a different scenario and are only an optional evidence deep dive. No customer claim, new cloud execution, successful attestation, completed sync or Phase A IAM is implied.

Rewrite this page and its local documentation; update the RFC entry link. Keep the full demo unchanged. Commit and push `feat/rfc-bq-vp-story`, create a PR against `main`, save the actual session ID under `/tmp/okf-vp-story/`, and report PR URL and HEAD. Do not merge.
