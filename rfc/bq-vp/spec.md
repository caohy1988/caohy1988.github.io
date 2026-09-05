# Spec — concrete story, deterministic graph retrieval

## Page contract

- Static HTML and page-local CSS at `/rfc/bq-vp/`. No JavaScript, external assets, build dependencies or cloud calls.
- Preserve the Alder/Maya board-pack lead, one arithmetic figure, three named runtime roles, one punchline and one VP ask. No stepper, drawers, matrix or alternative stories.
- Hero: illustrative label, Maya, Alder, the five-minute deadline, $4 million decision, 118% and 96%, all before architecture. Both percentages remain in the headline. The mistake must be visible from the arithmetic alone.
- Keep the $10m opening ARR, $9.6m same-customer closing ARR and erroneous $2.2m new-customer addition. All figures are invented.
- Target roughly 400–500 visible words and around two desktop viewports for a two-to-three-minute read. These are editorial/geometry checks, not measured human comprehension.

## First-class retrieval contract

- The “Why BigQuery” heading and role copy emphasize replayable context and deterministic OKF-graph retrieval, before metric execution.
- Catalog discovers/governs concepts and entries. Finding an entry is not the explicit traversal that selects the linked context.
- OKF authors definitions, relationships, computation declarations and versions. It is not itself a query engine for agents at scale; pinning belongs to the runtime.
- BigQuery hosts a projection of the graph and related facts. Retrieval uses a pinned publication plus explicit SQL or bounded graph walks, with deterministic query semantics.
- State the determinism boundary: fixed query, parameters, publication, fact versions, authorization scope and stable ordering yield the same selected context and result shape. Do not imply identical LLM answers or that a publication pin freezes fact tables.
- Contrast ranked document passages/model-chosen paths with explicit graph traversal. Do not claim all vector retrieval is inherently nondeterministic.
- Tie graph retrieval to Maya's retention definition, starting-cohort rule and declared computation.
- Distinguish proposed retrieval receipts (query, pins and selected context) from computation receipts (metric job, context and result). Retrieval alone does not prove the number; a substituted query or missing execution evidence leaves it unproven. Preserve agent/execution-identity attribution and IAM.
- Include a short empty-BigQuery case: the OKF graph projection and versioned facts can be the first workload, before a revenue warehouse. No projection means no BigQuery retrieval; do not make preexisting revenue data the reason BigQuery is useful.
- Use the exact punchline: **BigQuery turns the OKF graph into replayable context for agents.**

## Honesty and ask

- Keep the entire runtime explicitly labeled as an unbuilt RFC proposal. Direct/imperative descriptions within that scope are proposed responsibilities, not claims of delivered services.
- Footer explicitly labels Graph-over-OKF and retrieval receipts as RFC proposals, says no Alder query ran, and preserves existing demo stub/`UNVERIFIABLE` and unbuilt governed sync/Phase A IAM limitations. No `ATTESTED`, `BQ_COMMITTED` or Graph-completion claim.
- Preserve authored-bundle authority. Do not suggest a built Catalog-to-BigQuery import or invent job/session/receipt IDs.
- One Finance pilot: repeat pinned retrieval and compare context, then compute retention for one quarter of real pilot data. Withhold execution evidence and the number remains unproven. Do not impose Alder's invented 96% on the real pilot.
- Keep the optional `/rfc/full-demo/` link; its content and artifacts remain unchanged.

## Usability and delivery

- Semantic heading order, visible keyboard focus, working skip link and valid local links. No horizontal overflow at 1280, 768, 375 or 320 px; readable contrast and print view.
- Scope: `index.html`, optional page-local `styles.css`, and `STORY.md`, `intent.md`, `spec.md`, `plan.md` under `rfc/bq-vp/`. The existing illustrative RFC masthead blurb remains accurate.
- Commit and push `feat/rfc-bq-vp-det-retrieval`; create a PR against `main`. Save session and QA artifacts under `/tmp/okf-vp-det/`, report PR URL and HEAD, and do not merge.
