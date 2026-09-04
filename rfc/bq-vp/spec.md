# Spec — a story the VP can retell

## Page contract

- Static HTML and page-local CSS at `/rfc/bq-vp/`; no JavaScript, build, external assets or cloud calls.
- One continuous brief: the complete board-pack near-miss and arithmetic in the hero, the three named runtime roles, and one VP ask. The punchline follows the runtime section. No stepper, tabs, drawers, alternate scenarios or abstract benefit cards as the lead.
- At 1280 × 720 the first viewport must show the illustrative label, Maya's situation, both 118% and 96%, and why the first number was wrong. Target approximately two desktop viewport heights and roughly 400–500 visible words for a two-to-three-minute read. Reading time is an editorial estimate, not a user-study result.
- One arithmetic figure compares the 118% trap and the correct 96% side by side on desktop and stacked on mobile. Label the $9.6m from the same customers, mark the extra $2.2m from new customers as the mistake, and show both numerators divided by the $10m opening cohort. It is a board-pack illustration, not a rendered execution receipt.
- The hero itself names Maya, Alder, the five-minute deadline, the $4 million decision, and both 118% and 96%. Both percentages are in the headline. No architecture language precedes these facts. The headline, highlighted story facts and arithmetic labels must explain the near-miss on a 30-second skim.
- Define ARR and expand OKF on first use. Explain retention through the same-customer arithmetic.

## Runtime and evidence contract

- Explicitly label the entire technical section as an unbuilt RFC proposal. Use direct, imperative descriptions of the proposed responsibilities; do not repeat conditional boilerplate in each sentence. The story is direct under its illustrative label.
- Explicitly distinguish Knowledge Catalog (find the approved definition), OKF (authored definition, query and parameters), and BigQuery (execution, computation receipt, attribution and IAM). Explain that Catalog alone does not run the calculation or bind its answer to a query job.
- Give BigQuery the most space. In this illustrative scenario Alder already keeps revenue data there, with query jobs and data access controls. State what the runtime adds relative to discovery without claiming a universal database monopoly.
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

Only the requested page and its `intent.md`, `spec.md`, `plan.md`, and `STORY.md` change in this follow-up. The RFC entry link remains accurate. QA artifacts and actual session identifiers go in `/tmp/okf-vp-story/`. Commit and push `feat/rfc-bq-vp-story` to existing PR 20; report its URL and the new HEAD. Do not open a second PR or merge.
