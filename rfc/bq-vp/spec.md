# Spec — a story the VP can retell

## Page contract

- Static HTML and page-local CSS at `/rfc/bq-vp/`; no JavaScript, build, external assets or cloud calls.
- One continuous brief with four sections: the board-pack moment, the near-miss, three proposed runtime beats, and one VP ask. The punchline follows the runtime section. No stepper, tabs, drawers, alternate scenarios or abstract benefit cards as the lead.
- At 1280 × 720 the first viewport must show the illustrative label, Maya's situation, both 118% and 96%, and why the first number was wrong. Target approximately two desktop viewport heights and 400–550 visible words for a two-to-three-minute read. Reading time is an editorial estimate, not a user-study result.
- A clearly labeled arithmetic figure shows the $10.0m opening cohort, $9.6m same-customer closing ARR, $2.2m new-customer ARR, and both calculations. It is a board-pack illustration, not a rendered execution receipt.
- The company, persona, deadline and $4 million decision are concrete. The story comes before the Knowledge Catalog + OKF / BigQuery thesis.
- Define ARR and expand OKF on first use. Explain retention through the same-customer arithmetic.

## Runtime and evidence contract

- Explicitly label the entire counterfactual “RFC proposal, not built”; use conditional language.
- Tie discovery to Finance's approved OKF definition and declared computation, context pinning to a revision held fixed for the run, and the computation receipt to the revision, quarter parameters, BigQuery job and result.
- Missing execution evidence must leave the answer unproven. A citation or pinned context alone does not verify it.
- Make the agent and its execution identity attributable under explicit access grants. Preserve the historical context; do not promise arbitrary data replay or identical answers across agents.
- Keep v1 source-bundle authority intact; never imply an automatic Catalog-to-BigQuery import or an existing built-in runtime service.
- Label the invented scenario before the headline and distinguish it from evidence in the footer. Do not borrow session IDs or recordings to support the Alder numbers.
- Footer: no Alder query ran; the runtime is proposed; demo attesters are stubs and receipts are `UNVERIFIABLE`; governed sync and Phase A IAM remain unbuilt. No claims of `ATTESTED`, `BQ_COMMITTED` or Phase A completion.
- Offer `/rfc/full-demo/` as a separate recorded evidence deep dive with limitations. Its content and artifacts remain unchanged.

## Ask and usability

- Ask for one retention pilot with a Finance owner, one quarter of data, and a missing-receipt negative case.
- Make the RFC masthead link accurately describe the new story and illustrative status.
- Semantic headings, an accessible calculation figure, visible keyboard focus, working skip link, readable contrast and no mobile horizontal overflow at 375 px or 320 px. No essential content depends on color or script.
- Keep the print view legible. Avoid fixed/sticky elements covering text.

## Delivery

Only the requested page, its `intent.md`, `spec.md`, `plan.md`, `STORY.md`, and the one RFC entry link change. QA artifacts and actual session identifiers go in `/tmp/okf-vp-story/`. Commit, push `feat/rfc-bq-vp-story`, create a PR targeting `main`, report PR URL and HEAD, and do not merge.
